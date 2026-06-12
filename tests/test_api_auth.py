"""Auth wiring: env -> token -> Authorization header (so private posts are reachable)."""

import httpx
import pytest

from glowfic_tts import api
from glowfic_tts.api import client_from_env, login

_AUTH_ENV = ("GLOWFIC_API_TOKEN", "GLOWFIC_USERNAME", "GLOWFIC_PASSWORD")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _AUTH_ENV:
        monkeypatch.delenv(var, raising=False)


def _auth_header(client) -> str | None:
    return client._client.headers.get("Authorization")


def test_anonymous_when_no_env():
    with client_from_env() as client:
        assert _auth_header(client) is None


def test_explicit_token_wins_and_skips_login(monkeypatch):
    monkeypatch.setenv("GLOWFIC_API_TOKEN", "tok-123")
    monkeypatch.setenv("GLOWFIC_USERNAME", "u")
    monkeypatch.setenv("GLOWFIC_PASSWORD", "p")
    monkeypatch.setattr(api, "login", lambda *a, **k: pytest.fail("login should not be called"))
    with client_from_env() as client:
        assert _auth_header(client) == "tok-123"


def test_username_password_exchanged_for_token(monkeypatch):
    seen = {}
    monkeypatch.setenv("GLOWFIC_USERNAME", "alice")
    monkeypatch.setenv("GLOWFIC_PASSWORD", "secret")

    def fake_login(username, password, *a, **k):
        seen["creds"] = (username, password)
        return "tok-from-login"

    monkeypatch.setattr(api, "login", fake_login)
    with client_from_env() as client:
        assert _auth_header(client) == "tok-from-login"
    assert seen["creds"] == ("alice", "secret")


@pytest.mark.parametrize("present", ["GLOWFIC_USERNAME", "GLOWFIC_PASSWORD"])
def test_partial_credentials_fail_loud(monkeypatch, present):
    monkeypatch.setenv(present, "x")
    with pytest.raises(RuntimeError, match="BOTH"):
        client_from_env()


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
