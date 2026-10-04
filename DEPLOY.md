# Deploy (Render.com — besplatno)

1. Napravi novi GitHub repo (npr. `jelovnik-service`) i ubaci u njega:
   - `app.py`
   - `requirements.txt`

2. Idi na https://render.com → sign up (može preko GitHub naloga) → **New +** → **Web Service**.

3. Poveži svoj GitHub repo.

4. Podešavanja:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free

5. **Environment Variables** (Render → tvoj servis → Environment):

   Za Anthropic (podrazumevano):
   - `ANTHROPIC_API_KEY` = tvoj Anthropic API ključ (console.anthropic.com → API Keys)
   - `ANTHROPIC_MODEL` (opciono) = npr. `claude-sonnet-5` (podrazumevano) ili `claude-haiku-4-5-20251001`

   Za Free.ai (besplatna alternativa):
   - `OCR_PROVIDER` = `freeai`
   - `FREE_AI_API_KEY` = tvoj Free.ai API ključ (free.ai/account/?tab=api)

   **Napomena:** tačan oblik Free.ai JSON odgovora za tabele nije bio javno
   dokumentovan u trenutku pisanja ovog servisa, pa postoji `/debug-ocr`
   endpoint koji pokazuje sirov odgovor i rezultat mapiranja na naš format
   (dani × obroci). Posle prvog deploy-a sa `OCR_PROVIDER=freeai`, otvori:
   `https://jelovnik-service.onrender.com/debug-ocr`
   i pošalji rezultat — ako mapiranje ne pogodi tačno, prilagodićemo
   `_grid_to_menu()` funkciju prema stvarnom obliku odgovora.

6. Klikni **Create Web Service**. Za par minuta dobićeš URL oblika:
   `https://jelovnik-service.onrender.com`

7. Test u browseru:
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic` → redirect na sliku jelovnika
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic/danas` → JSON sa jelima za danas (AI pročita tabelu sa slike)
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic/nedelja` → cela nedeljna tabela

## Cena AI čitanja

Tabela se čita samo jednom nedeljno (keširano 7 dana), tako da je trošak
zanemarljiv — par centi mesečno na Anthropic API-ju.

## Napomena o besplatnom planu

Render-ov free web servis "zaspi" posle ~15 min neaktivnosti i prvi sledeći
zahtev ga budi (par sekundi kašnjenja). Za ovu namenu (slika koja se menja
jednom nedeljno) to je sasvim u redu.

## Alternative

- **PythonAnywhere** (besplatan tier, WSGI app, jednostavno za Flask)
- **Fly.io** (besplatan mali plan, malo više podešavanja)
- **Railway** (besplatan kredit mesečno)

Sve tri rade sa istim `app.py` fajlom, bez izmena.
