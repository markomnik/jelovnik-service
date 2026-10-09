# Deploy (Render.com — besplatno)

1. Napravi novi GitHub repo (npr. `jelovnik-service`) i ubaci u njega:
   - `app.py`
   - `requirements.txt`

2. Idi na https://render.com → sign up (može preko GitHub naloga) → **New +** → **Web Service**.

3. Poveži svoj GitHub repo.

4. Podešavanja:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --timeout 120`

   (Podrazumevani gunicorn worker timeout je 30s, a OCR obrada slike kod
   freeocr.ai/anthropic-a može trajati duže od toga — bez ovoga gunicorn
   ubija worker usred zahteva i vraća goli "500" bez ikakve poruke.)
   - **Instance Type**: Free

5. **Environment Variables** (Render → tvoj servis → Environment):

   Za Anthropic (podrazumevano):
   - `ANTHROPIC_API_KEY` = tvoj Anthropic API ključ (console.anthropic.com → API Keys)
   - `ANTHROPIC_MODEL` (opciono) = npr. `claude-sonnet-5` (podrazumevano) ili `claude-haiku-4-5-20251001`

   Za Free.ai (besplatna alternativa, ali besplatni model slabo čita ćirilicu):
   - `OCR_PROVIDER` = `freeai`
   - `FREE_AI_API_KEY` = tvoj Free.ai API ključ (free.ai/account/?tab=api)

   Za freeocr.ai (preporučeno — dobro dokumentovan API, 50 besplatnih poziva
   pri registraciji, zatim $1 / 500 poziva — naša potrošnja je ~4 poziva
   mesečno, pošto se tabela kešira 7 dana):
   - `OCR_PROVIDER` = `freeocr`
   - `FREEOCR_API_KEY` = tvoj API ključ sa freeocr.ai/platform/keys

   Google Calendar (vrednosti dobijaš iz `get_refresh_token.py`):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`
   - `GOOGLE_CALENDAR_ID` (opciono, podrazumevano `primary`)

   Endpoint: `GET /calendar/next-days` (danas + 3 naredna dana, kod je u
   `calendar_routes.py`). Sve tri Google vrednosti su tajne - samo u Render
   Environment, nikad u repozitorijum.

   Bezbednost:
   - `ADMIN_TOKEN` = bilo koja duga nasumična vrednost (npr. generiši sa
     `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`).
     Bez ovoga, `/debug` i `/debug-ocr` su potpuno ugašeni (vraćaju 404) —
     to su interni dijagnostički endpointi koji realno troše novac
     (pokreću OCR poziv), pa ne treba da budu javno dostupni. Sa tokenom,
     pristupaš im kao `.../debug-ocr?token=TVOJ_TOKEN`.
   - `ALLOWED_ORIGIN` (opciono) = tačan origin tvoje objavljene stranice
     (npr. `https://claude.site`), umesto podrazumevanog `*`. Suzuje ko
     sme da pročita JSON odgovor preko browser fetch-a sa druge stranice.
     Nije kritično (podaci nisu osetljivi), ali je dobra praksa.

   **Napomena (Free.ai):** tačan oblik Free.ai JSON odgovora za tabele nije bio
   javno dokumentovan u trenutku pisanja, pa postoji `/debug-ocr` endpoint koji
   pokazuje sirov odgovor i rezultat mapiranja na naš format (dani × obroci).
   `/debug-ocr` radi i za `freeocr` provider — otvori ga posle deploy-a i
   pošalji rezultat ako mapiranje ne pogodi dane/obroke tačno.

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
