"""
Flask ekstenzije koje koristi više modula.

Limiter je ovde, a ne u app.py, da blueprint-i mogu da ga uvezu (npr. za stroži limit na
jednom endpointu) bez kružnog uvoza. Povezuje se sa aplikacijom u app.create_app().
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60 per hour"])
