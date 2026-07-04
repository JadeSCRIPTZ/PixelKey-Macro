# PixelKey Macro

Un macro de tastatură pentru PC cu declanșare prin detecție de culoare de pixel.

## Funcții

- **Secvență de pași personalizată**: adaugi câte pași vrei, în ordinea dorită:
  - `Hold Key` — ține apăsată o tastă pentru N secunde/minute
  - `Press Key` — apasă și eliberează o tastă, cu pauză configurabilă după
  - Poți bifa **Loop** ca secvența să se repete continuu până apeși Stop
- **Pixel Color Trigger**: alegi un pixel de pe ecran (coordonate X/Y) + o culoare țintă + toleranță. Când culoarea de pe acel pixel se potrivește, secvența pornește automat.
- **Hotkeys globale**: Start (implicit `F6`) și Stop (implicit `F7`), configurabile din tab-ul Settings.
- Config salvat automat (`~/.pixelkey_macro_config.json`) — se reîncarcă la următoarea pornire.

## Exemplu de utilizare (farming loop)

1. Adaugi pas: `Hold "a"` — 2 minute
2. Adaugi pas: `Press "w"` — 3 secunde
3. Adaugi pas: `Press "d"` — 1.5 secunde
4. Bifezi **Loop sequence** dacă vrei să se repete la infinit
5. Apeși **Start** (sau F6) — sau activezi Pixel Trigger ca să pornească automat când apare o culoare anume pe ecran (ex: un fish bobber, un indicator de resursă etc.)

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
