"""Shared pytest setup.

Sets a test environment and makes the Flask app importable on Python 3.13
test runners, where the stdlib ``audioop`` module (imported transitively by
discord.py 2.3.2) has been removed.
"""
import os
import sys
import tempfile
import types

# Python 3.13 removed stdlib ``audioop``; discord.py 2.3.2 imports it. Provide a
# harmless stub so modules that transitively import discord stay importable in
# tests. On the production runtime (older Python) the real module is used.
if "audioop" not in sys.modules:
    try:
        import audioop  # noqa: F401
    except ModuleNotFoundError:
        _stub = types.ModuleType("audioop")
        _stub.__getattr__ = lambda name: (lambda *a, **k: None)  # type: ignore[attr-defined]
        sys.modules["audioop"] = _stub

# Test environment — set before the app module is imported.
os.environ.setdefault("BREXIS_DISABLE_BACKGROUND", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-prod")
os.environ.setdefault("BREXIS_PIN", "1357")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")  # test client speaks http
os.environ.setdefault("LOGIN_MAX_ATTEMPTS", "3")
os.environ.setdefault("LOGIN_LOCKOUT_SECONDS", "60")
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.gettempdir(), "brexis_test.db"),
)
