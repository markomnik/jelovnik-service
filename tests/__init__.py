"""
Testovi (unittest iz standardne biblioteke; rade i sa pytest-om).

Pokretanje iz korena projekta:
    python -m unittest discover -s tests -t .

Mreža se u testovima nikad ne koristi: HTTP pozivi se zamenjuju lažnim odgovorima.

Ako flask-limiter nije instaliran (npr. u okruženju za brzu proveru), ubacuje se minimalna
zamena da bi se aplikacija mogla sastaviti. Nakon `pip install -r requirements.txt` koristi se
prava biblioteka, i tada se ograničenje broja zahteva isključuje preko RATELIMIT_ENABLED.
"""

import sys
import types

try:
    import flask_limiter  # noqa: F401
except ImportError:
    _module = types.ModuleType("flask_limiter")
    _util = types.ModuleType("flask_limiter.util")

    class _FakeLimiter:
        def __init__(self, *args, **kwargs):
            pass

        def init_app(self, app):
            pass

        def exempt(self, obj):
            return obj

        def limit(self, *args, **kwargs):
            return lambda fn: fn

    _module.Limiter = _FakeLimiter
    _util.get_remote_address = lambda: "127.0.0.1"
    sys.modules["flask_limiter"] = _module
    sys.modules["flask_limiter.util"] = _util
