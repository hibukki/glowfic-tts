"""Glowfic JSON API: raw response models + a network-only client adapter.

The adapter only turns HTTP into parsed objects. It never touches disk and does
no caching — the orchestrator owns the per-page cache loop.

API shape (probed against https://glowfic.com/api/v1, 2026-05):
- GET /posts/{id}            -> a post object (opening post = seq 0)
- GET /posts/{id}/replies    -> a plain JSON *list* of replies;
                                pagination is in response headers Page/Per-Page/Total.
- POST /login {username,password} -> {token}; send it back as the `Authorization`
                                header to read posts that aren't public (403 otherwise).
                                Token is a JWT and can expire — we just log in again.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .models import Coverage

DEFAULT_BASE_URL = "https://glowfic.com/api/v1"
DEFAULT_USER_AGENT = "glowfic-tts/0.1 (personal audiobook tool)"

# glowfic rate-limits bursts (429); these are transient, so back off and retry.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_BACKOFF = 120.0
_EXP_BACKOFF = wait_exponential(multiplier=2, min=5, max=_MAX_BACKOFF)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


def _raise_for_status(r: httpx.Response) -> None:
    """Like httpx's raise_for_status, but the error carries the *full* response body
    (loud errors) and stays an HTTPStatusError, so 429/5xx remain retryable."""
    if r.is_error:
        raise httpx.HTTPStatusError(
            f"{r.request.method} {r.request.url} -> HTTP {r.status_code}: {r.text}",
            request=r.request, response=r,
        )


def _wait_retry_after(retry_state) -> float:
    """Wait as long as glowfic's `Retry-After` asks (it knows its own throttle window),
    else exponential backoff — capped either way so one request can't hang the build."""
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), _MAX_BACKOFF)
    return _EXP_BACKOFF(retry_state)


_retry = retry(
    retry=retry_if_exception(_is_retryable),
    wait=_wait_retry_after,
    stop=stop_after_attempt(8),
    reraise=True,
)


class _Lax(BaseModel):
    # Ignore unknown fields so new API fields don't break us; required fields
    # still validate, which is what catches real drift.
    model_config = ConfigDict(extra="ignore")


class RawCharacter(_Lax):
    id: int | None = None
    name: str | None = None
    screenname: str | None = None


class RawIcon(_Lax):
    id: int | None = None
    url: str | None = None
    keyword: str | None = None


class RawUser(_Lax):
    id: int | None = None
    username: str


class RawApiPost(_Lax):
    id: int
    subject: str
    authors: list[RawUser]
    num_replies: int
    content: str
    character: RawCharacter | None = None
    icon: RawIcon | None = None


class RawApiReply(_Lax):
    id: int
    content: str
    character_name: str | None = None
    character: RawCharacter | None = None
    icon: RawIcon | None = None
    user: RawUser


class PageMeta(BaseModel):
    page: int
    per_page: int
    total: int


class RawPost(BaseModel):
    """The cached fetch artifact: the post plus every reply we pulled, in order."""

    coverage: Coverage
    post: RawApiPost
    replies: list[RawApiReply]


class GlowficClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = 1.0,
        timeout: float = 30.0,
        token_provider: Callable[[], str | None] | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url, headers={"User-Agent": user_agent}, timeout=timeout
        )
        self._delay = delay_seconds
        # Resolved once, lazily, on the first network request (see _authenticate),
        # so a fully cached run — and `cast` re-runs — never has to log in.
        self._token_provider = token_provider
        self._authed = False

    def _authenticate(self) -> None:
        """Attach the Authorization header on first use. Lazy on purpose: keeps the
        'fetch hits the network only on a miss' contract — a cached/offline run that
        never makes a request never logs in. The server reads the last space-split
        field of Authorization, so a bare token works."""
        if self._authed:
            return
        if self._token_provider:
            token = self._token_provider()
            if token:
                self._client.headers["Authorization"] = token
        self._authed = True

    def _request(self, path: str, params: dict | None = None) -> httpx.Response:
        # Auth sits outside the retry: login has its own backoff, and a terminal
        # login failure must not be re-tried as if it were a flaky GET.
        self._authenticate()
        return self._get(path, params)

    @_retry
    def _get(self, path: str, params: dict | None) -> httpx.Response:
        time.sleep(self._delay)
        r = self._client.get(path, params=params)
        _raise_for_status(r)
        return r

    def get_post(self, post_id: int) -> RawApiPost:
        return RawApiPost.model_validate(self._request(f"/posts/{post_id}").json())

    def get_replies_page(
        self, post_id: int, page: int, per_page: int = 100
    ) -> tuple[list[RawApiReply], PageMeta]:
        r = self._request(
            f"/posts/{post_id}/replies", params={"page": page, "per_page": per_page}
        )
        replies = [RawApiReply.model_validate(item) for item in r.json()]
        meta = PageMeta(
            page=int(r.headers["Page"]),
            per_page=int(r.headers["Per-Page"]),
            total=int(r.headers["Total"]),
        )
        return replies, meta

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GlowficClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@_retry
def login(
    username: str,
    password: str,
    base_url: str = DEFAULT_BASE_URL,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> str:
    """Exchange glowfic credentials for an API token (a JWT). Backs off on transient
    throttling/5xx like every other call; a real failure (e.g. wrong password) raises
    loudly with the full response body."""
    r = httpx.post(
        f"{base_url}/login",
        data={"username": username, "password": password},
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    _raise_for_status(r)
    return r.json()["token"]


class _GlowficAuth(BaseSettings):
    """Glowfic credentials from the environment and a local .env file (so no manual
    `source .env` is needed). GLOWFIC_API_TOKEN / GLOWFIC_USERNAME / GLOWFIC_PASSWORD;
    a real env var overrides the .env file."""

    model_config = SettingsConfigDict(env_prefix="GLOWFIC_", env_file=".env", extra="ignore")
    api_token: str | None = None
    username: str | None = None
    password: str | None = None


def client_from_env() -> GlowficClient:
    """A client authenticated from the environment, so private posts are reachable.

    GLOWFIC_API_TOKEN (a token you already hold) wins; else GLOWFIC_USERNAME +
    GLOWFIC_PASSWORD are exchanged for one via /login. Setting only one of the
    pair is a mistake, not "go anonymous" — it fails loudly. Nothing set -> an
    anonymous client (public posts only).

    Credential *validation* is eager (a config error should surface immediately),
    but the /login network call is deferred to the client's first request, so a
    fully cached run never logs in."""
    auth = _GlowficAuth()
    token = auth.api_token or None
    username = auth.username or None
    password = auth.password or None
    if not token and (bool(username) != bool(password)):
        raise RuntimeError(
            "glowfic auth: set BOTH GLOWFIC_USERNAME and GLOWFIC_PASSWORD "
            "(or a pre-obtained GLOWFIC_API_TOKEN), not just one."
        )
    if token:
        provider: Callable[[], str | None] | None = lambda: token
    elif username and password:
        provider = lambda: login(username, password)
    else:
        provider = None
    return GlowficClient(token_provider=provider)
