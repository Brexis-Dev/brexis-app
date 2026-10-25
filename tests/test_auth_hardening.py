"""SECRET_KEY and PIN hardening (fail closed, no known defaults)."""
import os

import pytest


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_failures():
    import app as app_module

    app_module._LOGIN_FAILURES.clear()
    yield
    app_module._LOGIN_FAILURES.clear()


def test_secret_key_is_not_the_old_constant():
    from app import app

    assert app.secret_key not in (None, "", "brexis-dev-secret")


def test_secret_key_uses_env_when_set():
    from app import app

    assert app.secret_key == os.environ["SECRET_KEY"]


def test_no_insecure_defaults_in_source():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    assert "brexis-dev-secret" not in src
    assert '"3628"' not in src  # the old PIN fallback


def test_correct_pin_still_authenticates(client):
    resp = client.post("/", data={"pin": "1357"})  # conftest sets this PIN
    assert resp.status_code == 302
    assert "/chat" in resp.headers["Location"]


def test_login_disabled_when_pin_unset(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "BREXIS_PIN", "")
    # Neither an empty submission nor any value may authenticate.
    assert client.post("/", data={"pin": ""}).status_code == 200
    assert client.post("/", data={"pin": "guess"}).status_code == 200
