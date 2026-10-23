"""
Jednokratna skripta za dobijanje Google Calendar refresh token-a (čitanje i upis događaja).

POKRENI LOKALNO na svom računaru (ne na Render-u) - otvara browser za login.

Priprema:
  1. pip install google-auth-oauthlib
  2. U Google Cloud Console -> APIs & Services -> Credentials -> tvoj OAuth client
     (tip: Desktop app) -> Download JSON, sačuvaj kao `client_secret.json`
     u isti folder gde je ova skripta (scripts/). Fajl je u .gitignore, ne ide na GitHub.
  3. iz korena projekta: python3 scripts/get_refresh_token.py
  4. U browseru se prijavi kao day.info.screen@gmail.com i odobri pristup.

Na kraju skripta ispisuje tri vrednosti koje ide u Render environment variables:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
Tretiraj ih kao lozinke: ne commit-uj ih na GitHub i ne deli ih.
"""

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# calendar.events dozvoljava čitanje I upis događaja (Telegram bot upisuje događaje u kalendar)
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

SECRET_FILE = Path(__file__).with_name("client_secret.json")

flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)

# access_type=offline + prompt=consent garantuju da Google vrati refresh token
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

with open(SECRET_FILE) as f:
    cfg = json.load(f)
client = cfg.get("installed") or cfg.get("web") or {}

print("\n=== Kopiraj u Render -> Environment ===")
print(f"GOOGLE_CLIENT_ID={client.get('client_id')}")
print(f"GOOGLE_CLIENT_SECRET={client.get('client_secret')}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")

if not creds.refresh_token:
    print("\nUPOZORENJE: refresh token nije vraćen. Opozovi prethodni pristup na "
          "https://myaccount.google.com/permissions i pokreni skriptu ponovo.")
