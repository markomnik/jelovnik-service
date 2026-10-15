# Deploy (Render.com — besplatno)

1. Napravi novi GitHub repo (npr. `jelovnik-service`) i ubaci u njega ceo sadržaj ovog
   projekta: sve `.py` fajlove u korenu, `requirements.txt` i folder `tests/`
   (struktura je opisana na kraju ovog fajla).

2. Idi na https://render.com → sign up (može preko GitHub naloga) → **New +** → **Web Service**.

3. Poveži svoj GitHub repo.

4. Podešavanja:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --timeout 120`

   (Podrazumevani gunicorn worker timeout je 30s, a OCR obrada slike kod
   freeocr.ai može trajati duže od toga — bez ovoga gunicorn
   ubija worker usred zahteva i vraća goli "500" bez ikakve poruke.)
   - **Instance Type**: Free

5. **Environment Variables** (Render → tvoj servis → Environment):

   Za čitanje slika (jelovnik i pozivnice u Telegram botu), freeocr.ai — 50 besplatnih
   poziva pri registraciji, zatim $1 / 500 poziva; jelovnik troši ~4 poziva mesečno,
   pošto se tabela kešira 7 dana:
   - `FREEOCR_API_KEY` = tvoj API ključ sa freeocr.ai/platform/keys

   (Ranije podržani provajderi free.ai i Anthropic su uklonjeni, pa varijable
   `OCR_PROVIDER`, `FREE_AI_API_KEY`, `ANTHROPIC_API_KEY` i `ANTHROPIC_MODEL`
   više ne treba da postoje na Render-u; možeš da ih obrišeš.)

   Google Calendar (vrednosti dobijaš iz `get_refresh_token.py`):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`
   - `GOOGLE_CALENDAR_ID` (opciono, podrazumevano `primary`)

   Endpoint: `GET /calendar/next-days` (danas + 3 naredna dana, kod je u
   `calendar_routes.py`). Sve tri Google vrednosti su tajne - samo u Render
   Environment, nikad u repozitorijum.

   Telegram bot (pozivnice -> kalendar):
   - `TELEGRAM_BOT_TOKEN` = token od @BotFather (`/newbot`)
   - `TELEGRAM_WEBHOOK_SECRET` = tajni string, samo slova, brojevi, `_` i `-`
     (npr. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `TELEGRAM_ALLOWED_USER_IDS` = ID-jevi korisnika kojima je dozvoljeno upisivanje,
     odvojeni zarezom (npr. `123456789,987654321`). Samo oni mogu da šalju pozivnice
     i da potvrde upis dugmetom Da; ostalima bot ne odgovara. U privatnom čatu je
     korisnički ID isti kao ID čata. Ako nije podešen, važi samo `TELEGRAM_ALLOWED_CHAT_IDS`.
   - `TELEGRAM_ALLOWED_CHAT_IDS` (opciono) = dodatno ograničava u kojim čatovima bot
     radi (npr. samo jedna grupa). Ako su podešena oba spiska, korisnik mora da bude
     na spisku korisnika I čat na spisku čatova.
   - `FREEOCR_API_KEY` = isti freeocr.ai ključ kao za jelovnik, koristi se za slike
     pozivnica. Za tekst pozivnice bot ne zove nijedan spoljni servis.

   Upis događaja traži dozvolu pisanja: u `get_refresh_token.py` je scope sada
   `calendar.events`. **Pokreni skriptu ponovo** i zameni `GOOGLE_REFRESH_TOKEN`
   novom vrednošću (stari token ima samo čitanje i upis bi vratio grešku 403).

   Povezivanje bota (jednom, posle deploy-a):
   1. Registruj webhook (zameni vrednosti u ugličastim zagradama):
      ```
      curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
        -d "url=https://jelovnik-service.onrender.com/telegram/webhook" \
        -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>" \
        -d 'allowed_updates=["message","callback_query"]'
      ```
      Odgovor treba da bude `{"ok":true,...}`.
   2. U Telegramu pošalji botu `/start`. Odgovoriće tvojim korisničkim ID-jem; upiši ga u
      `TELEGRAM_ALLOWED_USER_IDS` na Render-u (servis se restartuje). Isto uradi i za
      svakog dodatnog korisnika: neka pošalje `/start` i dobije svoj ID.
   3. Pošalji botu tekst ili sliku pozivnice. Dobijaš predlog sa dugmadima Da/Ne.

   Kako bot čita pozivnice:
   - **Slika**: freeocr.ai `/extract` (AI izvlači naslov, datum, vreme, lokaciju i
     detalje). Ako datum ili naslov fale, dodatno se zove `/ocr` (ceo tekst sa
     slike), pa se tekst čita pravilima kao i obična poruka. Do 2 poziva po slici.
   - **Tekst** (i opis uz sliku): pravila za srpske datume i vreme, bez AI-ja.
     Razume npr. `10.10.2026.`, `31. oktobra`, `sutra`, `u subotu`, `18h`, `18:30`,
     `18.30h`, `od 21 do 02h`, labele `Mesto:` i `Naslov:`, i ćirilicu.
     Pravila su jednostavnija od AI-ja: kad nešto pogreše ili izostave (naslov,
     lokacija), to se vidi u predlogu, a ti odbiješ sa Ne i pošalješ jasniju poruku.
   - Naslovi i lokacije u kalendaru su uvek latinica.

   Napomene: na besplatnom Render planu servis zaspi posle ~15 min, pa prva poruka
   može da kasni do minut-dva (Telegram je ponovi sam). Predlozi koji čekaju
   potvrdu drže se u memoriji, pa se gube ako se servis restartuje između
   slanja pozivnice i klika na Da; tada samo pošalji pozivnicu ponovo.

   Bezbednost:
   - `ADMIN_TOKEN` = bilo koja duga nasumična vrednost (npr. generiši sa
     `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`).
     Bez ovoga, `/debug` i `/debug-ocr` su potpuno ugašeni (vraćaju 404) —
     to su interni dijagnostički endpointi koji realno troše novac
     (`/debug-ocr` pokreće OCR poziv), pa ne treba da budu javno dostupni. Sa tokenom,
     pristupaš im kao `.../debug-ocr?token=TVOJ_TOKEN` (ili zaglavljem `X-Admin-Token`).
     `/debug-ocr` pokazuje sirov odgovor freeocr.ai-ja i rezultat mapiranja dana i obroka.
   - `ALLOWED_ORIGIN` (opciono) = tačan origin tvoje objavljene stranice
     (npr. `https://claude.site`), umesto podrazumevanog `*`. Suzuje ko
     sme da pročita JSON odgovor preko browser fetch-a sa druge stranice.
     Nije kritično (podaci nisu osetljivi), ali je dobra praksa.

6. Klikni **Create Web Service**. Za par minuta dobićeš URL oblika:
   `https://jelovnik-service.onrender.com`

7. Test u browseru:
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic` → redirect na sliku jelovnika
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic/danas` → JSON sa jelima za danas (AI pročita tabelu sa slike)
   - `https://jelovnik-service.onrender.com/jelovnik/vrtic/nedelja` → cela nedeljna tabela

## Cena AI čitanja

Tabela se čita samo jednom nedeljno (keširano 7 dana), tako da je trošak
zanemarljiv: oko 4 OCR poziva mesečno (plus do 2 po svakoj slici pozivnice u botu).

## Napomena o besplatnom planu

Render-ov free web servis "zaspi" posle ~15 min neaktivnosti i prvi sledeći
zahtev ga budi (par sekundi kašnjenja). Za ovu namenu (slika koja se menja
jednom nedeljno) to je sasvim u redu.

## Alternative

- **PythonAnywhere** (besplatan tier, WSGI app, jednostavno za Flask)
- **Fly.io** (besplatan mali plan, malo više podešavanja)
- **Railway** (besplatan kredit mesečno)

Sve tri rade sa istim kodom, bez izmena (start komanda je `gunicorn app:app`).

## Struktura projekta

```
app.py               sastavlja aplikaciju (create_app); sve ostalo je u modulima
config.py            vremenska zona (Europe/Belgrade) i nazivi dana
extensions.py        limiter (ograničenje broja zahteva)
security.py          bezbednosna zaglavlja/CORS i zaštita admin endpointa tokenom

menu_routes.py       rute /jelovnik/vrtic, /jelovnik/vrtic/danas, /jelovnik/vrtic/nedelja
menu_service.py      keš: URL slike (6h) i pročitana tabela (7 dana)
menu_scraper.py      pronalazi sliku jelovnika na sajtu vrtića
menu_table.py        tabela sa slike -> dani i obroci (latinica)
admin_routes.py      / (health), /debug, /debug-ocr

calendar_routes.py   Google Calendar: /calendar/next-days i upis događaja

telegram_routes.py   Telegram bot: samo prima i proverava zahtev (/telegram/webhook)
telegram_handlers.py obrada poruka i klikova Da/Ne (poslovna logika bota)
telegram_proposals.py  tekst predloga i predlozi koji čekaju potvrdu
telegram_auth.py     ko sme da koristi bota (TELEGRAM_ALLOWED_*_IDS)
telegram_api.py      pozivi ka Telegram Bot API-ju

event_parser.py      pozivnica (tekst ili slika) -> parametri događaja; povezuje delove ispod
event_text.py        tekst -> polja (pravila za srpski)
event_datetime.py    datumi i vremena u tekstu (10.10., sutra, u subotu, 18h, 18:30...)
event_image.py       slika -> polja (freeocr.ai /extract, rezerva /ocr)
event_fields.py      spajanje polja iz više izvora
event_normalize.py   provera polja i računanje početka i kraja
event_errors.py      ParseError (poruka se sme prikazati korisniku)

freeocr_client.py    klijent za freeocr.ai (koriste ga jelovnik i bot)
text_utils.py        transliteracija ćirilice u latinicu
get_refresh_token.py jednokratna skripta za Google token (pokreće se lokalno)
tests/               automatski testovi
```

## Testovi

Ne koriste mrežu (svi HTTP pozivi su zamenjeni lažnim odgovorima) i ne traže nikakve
ključeve. Iz korena projekta:

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

Pokreni ih posle svake izmene koda, pre push-a na GitHub.
