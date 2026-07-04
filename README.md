# PixelKey Macro

Un macro de tastatură pentru PC cu declanșare prin detecție de culoare de pixel.

## Funcții

- **Main Sequence**: adaugi câte pași vrei, în ordinea dorită:
  - `Hold Key` — ține apăsată o tastă pentru N secunde/minute
  - `Press Key` — apasă și eliberează o tastă, cu pauză configurabilă după
  - `Hold Right Click` / `Hold Left Click` — ține apăsat click-ul pentru N secunde
  - Poți bifa **Loop** ca secvența să se repete continuu până apeși Stop
- **Trigger Sequence**: o a doua listă de pași separată, care rulează O SINGURĂ DATĂ de fiecare dată când pixelul detectează culoarea setată.
- **Interrupt & Resume**: dacă pixelul detectează culoarea în timp ce ești, de exemplu, la secunda 40 din 50 la un `Hold "d"`, macroul:
  1. oprește imediat tasta `d`
  2. rulează integral Trigger Sequence (taste, click ținut etc.)
  3. reia `d` exact de unde a rămas, pentru cele 10 secunde rămase
  4. continuă normal cu restul pașilor din Main Sequence
  - Poți alege și modul „rulează Trigger Sequence și oprește tot" dacă nu vrei resume.
- **Pixel Color Trigger**: alegi un pixel de pe ecran (coordonate X/Y) + o culoare țintă + toleranță + cooldown (ca să nu se retrigger-eze instant).
- **Consolă live**: în partea de jos a aplicației vezi exact ce face macroul în timp real (ce pas rulează, când a detectat culoarea, orice eroare).
- **Hotkeys globale**: Start (implicit `F6`) și Stop (implicit `F7`), configurabile din tab-ul Settings.
- Config salvat automat (`~/.pixelkey_macro_config.json`) — se reîncarcă la următoarea pornire.

## Exemplu de utilizare (farming + reacție la pixel)

**Main Sequence:**
1. `Hold "a"` — 2 minute
2. `Press "w"` — 3 secunde
3. `Hold "d"` — 50 secunde

**Trigger Sequence** (rulează când pixelul detectează culoarea, indiferent unde ești în Main Sequence):
1. `Press "e"`
2. `Press "r"`
3. `Press "q"`
4. `Hold Right Click` — 2 secunde
5. `Press "f"`

Dacă pixelul detectează culoarea la secunda 40 din cele 50 de `Hold "d"`, macroul oprește `d`, rulează cei 5 pași de mai sus, apoi reia `d` pentru încă 10 secunde, apoi trece la pasul următor din Main Sequence.

## Descărcare versiuni anterioare

Fiecare versiune nouă publicată apare ca **Release separat** pe GitHub (`v1.0.0`, `v1.1.0`, ...) — toate rămân disponibile în secțiunea **Releases**, poți descărca oricare dintre ele oricând.

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
