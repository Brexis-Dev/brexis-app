"""Security response headers and session-cookie hardening."""
import pytest


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


def test_baseline_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_session_cookie_flags_configured():
    from app import app

    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_session_cookie_secure_reflects_env():
    # conftest sets SESSION_COOKIE_SECURE=0 for the http test client, so the
    # flag must be False here. In production the var is unset -> True.
    import os

    from app import app

    assert os.environ["SESSION_COOKIE_SECURE"] == "0"
    assert app.config["SESSION_COOKIE_SECURE"] is False
