"""Login brute-force throttle. conftest sets LOGIN_MAX_ATTEMPTS=3."""
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


def test_wrong_pin_locks_out_after_max_attempts(client):
    # First MAX attempts return the normal 200 "incorrect" page.
    for _ in range(3):
        resp = client.post("/", data={"pin": "0000"})
        assert resp.status_code == 200

    # The next attempt is locked out with 429 — even if the PIN were correct.
    resp = client.post("/", data={"pin": "1357"})
    assert resp.status_code == 429
    assert b"Too many attempts" in resp.data


def test_correct_pin_before_lockout_authenticates(client):
    client.post("/", data={"pin": "9999"})  # one failure, under the limit
    resp = client.post("/", data={"pin": "1357"})  # correct PIN
    assert resp.status_code == 302
    assert "/chat" in resp.headers["Location"]


def test_successful_login_clears_failure_counter(client):
    import app as app_module

    client.post("/", data={"pin": "0000"})
    client.post("/", data={"pin": "1357"})  # success clears the counter
    assert app_module._LOGIN_FAILURES == {}
