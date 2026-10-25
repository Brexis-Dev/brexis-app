"""Smoke test: the app imports under the test harness and /health responds."""


def test_app_imports_and_health():
    from app import app

    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert b"OK" in resp.data
