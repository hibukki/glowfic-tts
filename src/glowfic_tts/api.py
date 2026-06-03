"""Glowfic JSON API: raw response models + a network-only client adapter.

The adapter only turns HTTP into parsed objects. It never touches disk and does
no caching — the orchestrator owns the per-page cache loop.

API shape (probed against https://glowfic.com/api/v1, 2026-05):
- GET /posts/{id}            -> a post object (opening post = seq 0)
- GET /posts/{id}/replies    -> a plain JSON *list* of replies;
                                pagination is in response headers Page/Per-Page/Total.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, ConfigDict
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .models import Coverage

DEFAULT_BASE_URL = "https://glowfic.com/api/v1"
DEFAULT_USER_AGENT = "glowfic-tts/0.1 (personal audiobook tool)"

# glowfic rate-limits bursts (429); these are transient, so back off and retry.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


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
    ):
        self._client = httpx.Client(
            base_url=base_url, headers={"User-Agent": user_agent}, timeout=timeout
        )
        self._delay = delay_seconds

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _request(self, path: str, params: dict | None = None) -> httpx.Response:
        time.sleep(self._delay)
        r = self._client.get(path, params=params)
        r.raise_for_status()
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
