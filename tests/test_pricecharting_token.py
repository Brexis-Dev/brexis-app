"""PriceCharting must not carry a hardcoded token and must require a key."""
import os


def test_no_hardcoded_token_in_source():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gateway.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    assert "c0b53bce27c1bdab90b1605249e600dc43dfd1d5" not in src
    assert "_PC_DEMO_TOKEN" not in src


def test_fetch_requires_configured_key(monkeypatch):
    import gateway

    monkeypatch.setattr(gateway.db, "get_config", lambda key: None)
    result = gateway.fetch_pricecharting("Zelda", "Switch")
    assert result["found"] is False
    assert "not configured" in result["error"]
