"""The production debug endpoints must no longer exist."""
import pytest

REMOVED = [
    "/api/debug/relay-url",
    "/api/debug/execute-tool",
    "/api/debug/execute-send-to-printer",
    "/api/debug/relay-ping",
]


@pytest.fixture
def client():
    from app import app

    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("path", REMOVED)
def test_debug_endpoint_gone(client, path):
    assert client.get(path).status_code == 404


def test_no_debug_route_registered():
    from app import app

    rules = {r.rule for r in app.url_map.iter_rules()}
    assert not any(r.startswith("/api/debug/") for r in rules)
