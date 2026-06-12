"""Auth wiring: env -> token -> Authorization header (so private posts are reachable),
with login deferred to the first network call (cached runs must not log in)."""

import httpx
import pytest

from glowfic_tts import api, pipeline
from glowfic_tts.api import GlowficClient, RawApiPost, RawUser, client_from_env, login
from glowfic_tts.models import Coverage
from glowfic_tts.storage import Storage

_AUTH_ENV = ("GLOWFIC_API_TOKEN", "GLOWFIC_USERNAME", "GLOWFIC_PASSWORD")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _AUTH_ENV:
        monkeypatch.delenv(var, raising=False)


def _resolve(client) -> str | None:
    """Force the lazy auth the first network request would trigger, then read the header."""
    client._authenticate()
    return client._client.headers.get("Authorization")


def test_anonymous_when_no_env():
    with client_from_env() as client:
        assert _resolve(client) is None


def test_explicit_token_wins_and_skips_login(monkeypatch):
    monkeypatch.setenv("GLOWFIC_API_TOKEN", "tok-123")
    monkeypatch.setenv("GLOWFIC_USERNAME", "u")
    monkeypatch.setenv("GLOWFIC_PASSWORD", "p")
    monkeypatch.setattr(api, "login", lambda *a, **k: pytest.fail("login should not be called"))
    with client_from_env() as client:
        assert _resolve(client) == "tok-123"


def test_login_is_lazy_and_exchanges_credentials(monkeypatch):
    calls = []
    monkeypatch.setenv("GLOWFIC_USERNAME", "alice")
    monkeypatch.setenv("GLOWFIC_PASSWORD", "secret")
    monkeypatch.setattr(api, "login", lambda u, p, *a, **k: calls.append((u, p)) or "tok-from-login")
    with client_from_env() as client:
        assert calls == []  # deferred: no login at construction
        assert _resolve(client) == "tok-from-login"
    assert calls == [("alice", "secret")]


@pytest.mark.parametrize("present", ["GLOWFIC_USERNAME", "GLOWFIC_PASSWORD"])
def test_partial_credentials_fail_loud(monkeypatch, present):
    monkeypatch.setenv(present, "x")
    with pytest.raises(RuntimeError, match="BOTH"):
        client_from_env()


def test_cached_fetch_never_logs_in(tmp_path):
    """The regression Codex flagged: creds set, but every artifact is cached, so
    run_fetch must complete without a single network call (here: without login)."""
    storage = Storage(7, Coverage.of(None), root=tmp_path)
    storage.save_raw_post(RawApiPost(id=7, subject="s", authors=[RawUser(username="u")], num_replies=0, content="<p>x</p>"))
    storage.save_raw_page(1, [])  # empty page ends the paging loop without a request

    def boom() -> str:
        raise AssertionError("a fully cached run must not log in")

    with GlowficClient(token_provider=boom) as client:
        raw = pipeline.run_fetch(storage, client, 7, None)
    assert raw.post.id == 7 and raw.replies == []


def test_login_posts_credentials_and_returns_token(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured.update(url=url, data=data)
        return httpx.Response(200, json={"token": "jwt-abc"})

    monkeypatch.setattr(api.httpx, "post", fake_post)
    token = login("bob", "pw")
    assert token == "jwt-abc"
    assert captured["url"].endswith("/login")
    assert captured["data"] == {"username": "bob", "password": "pw"}


def test_login_raises_with_body_on_error(monkeypatch):
    body = {"errors": [{"message": "You have entered an incorrect password."}]}
    monkeypatch.setattr(api.httpx, "post", lambda *a, **k: httpx.Response(401, json=body))
    with pytest.raises(RuntimeError, match="incorrect password"):
        login("bob", "wrong")
