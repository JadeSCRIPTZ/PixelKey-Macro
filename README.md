# PixelKey Macro

Un macro de tastatură pentru PC cu declanșare prin detecție de culoare de pixel.

## Funcții

- **Main Sequence**: `Hold Key`, `Press Key`, `Hold Right Click`, `Hold Left Click`, câți pași vrei, cu opțiune de Loop.
- **Idle Hold Mode**: alternativă simplă — ține apăsată o singură tastă continuu (ex. `f`), fără să construiești o secvență.
- **Trigger Sequence**: o listă separată de pași care rulează o dată, de fiecare dată când e detectată o culoare.
- **Multiple Pixel Watch Points**: poți urmări MAI MULTE puncte de pe ecran simultan, fiecare cu propria culoare țintă și toleranță — dacă oricare se potrivește, se declanșează reacția.
- **Interrupt & Resume**: pixelul întrerupe pasul curent (reține exact timpul rămas), rulează Trigger Sequence, apoi reia pasul de unde a rămas.
- **Randomizare (jitter)**: variază ușor duratele (±% configurabil) ca secvența să nu arate perfect robotică.
- **Dry Run (mod test)**: simulează tot în consolă, fără să apese nimic real — testezi în siguranță.
- **Profiluri**: salvezi configurația completă sub un nume (ex. "Farming", "Fishing") și comuți instant între ele.
- **Panic Key**: o tastă separată (implicit `ESC`) care oprește tot instant, orice s-ar întâmpla.
- **Consolă live**: vezi exact ce face macroul, pas cu pas, în timp real.
- **Hotkeys globale**: Start (`F6`), Stop (`F7`), Panic (`ESC`) — toate configurabile.
- Config salvat automat, se reîncarcă la pornire.

## Exemplu de utilizare (farming + reacție la pixel)

**Main Sequence:**
1. `Hold "a"` — 2 minute
2. `Press "w"` — 3 secunde
3. `Hold "d"` — 50 secunde

**Trigger Sequence** (rulează când oricare pixel urmărit detectează culoarea lui):
1. `Press "e"`
2. `Press "r"`
3. `Press "q"`
4. `Hold Right Click` — 2 secunde
5. `Press "f"`

Dacă pixelul detectează culoarea la secunda 40 din cele 50 de `Hold "d"`, macroul oprește `d`, rulează cei 5 pași de mai sus, apoi reia `d` pentru încă 10 secunde, apoi trece la pasul următor.

## Descărcare versiuni anterioare

Fiecare versiune nouă publicată apare ca **Release separat** pe GitHub (`v1.0.0`, `v1.1.0`, `v2.0.0`, ...) — toate rămân disponibile în secțiunea **Releases**, poți descărca oricare dintre ele oricând.

## Nou în v2.0.0

- **Mai multe puncte de pixel simultan** — adaugi câte puncte de pixel vrei (coordonate + culoare + toleranță proprii); dacă ORICARE se potrivește, se declanșează Trigger Sequence.
- **Profiluri** — salvezi tot setup-ul curent (secvențe, puncte de pixel, hotkeys, tot) sub un nume, apoi încarci alt profil instant din tab-ul Settings. Util dacă ai seturi diferite pentru farming, pescuit, etc.
- **Randomizare timing (±%)** — variază ușor duratele la rulare, ca să nu arate perfect robotic.
- **Dry Run (mod test)** — bifezi și macroul doar loghează ce AR face, fără să apese realmente ceva. Perfect pentru testare în siguranță.
- **Panic key** (implicit `Esc`) — oprește tot instant, indiferent de stare, separat de Stop normal.
- **Idle Hold Mode** (adăugat în v1.2.0) — ține apăsată o tastă continuu, independent de Main Sequence, cu pauză/reluare automată la trigger de pixel.

## Instalare

### Varianta rapidă (Windows)
Descarcă `PixelKeyMacro.exe` din secțiunea **Releases** — nu necesită Python instalat.

### Din surse
```bash
pip install -r requirements.txt
python pixelkey_macro.py
```

Necesită Python 3.9+.

## Notă

Rulează cu drepturi de Administrator pe Windows dacă hotkey-urile globale sau `keyboard`/`pyautogui` nu răspund în jocuri fullscreen.
