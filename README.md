# Wand-Play

Startet ein Spiel mit angehängtem [Wand](https://wand.gg)-Trainer per Kommandozeile.
Statt Wand zu öffnen, das Spiel in der Liste zu suchen und „Spielen" zu klicken:

```text
py wandplay.py "Black Flag"
```

Das Tool startet Wand (falls nötig), sucht den Titel in Wands Spieleliste und klickt
„Spielen". Wand selbst startet daraufhin das Spiel über Steam und hängt den Trainer an.

## Voraussetzungen

- Windows, Python 3.10+ (getestet mit 3.14.7)
- Wand installiert unter `%LOCALAPPDATA%\Wand\Wand.exe`
- `py -m pip install -r requirements.txt` (einzige Abhängigkeit: `uiautomation`)

Steam muss **nicht** separat angesteuert werden — das erledigt Wand.

## Benutzung

```text
py wandplay.py "Black Flag"     Teilname, Groß-/Kleinschreibung egal
py wandplay.py --dump           Wands Accessibility-Baum ausgeben
py wandplay.py --selftest       Namens-Matching prüfen
py wandplay.py --version        Versionsnummer ausgeben (auch -V)
```

Der Suchbegriff wird als Teilstring gegen Wands Spieleliste gematcht. Mehrere Treffer
ergeben eine nummerierte Auswahl:

```text
> py wandplay.py sim
6 matches for 'sim':
  1. PowerWash Simulator 2
  2. Deconstruction Simulator
  3. Cowboy Life Simulator
  4. Seafarer: The Ship Sim
  5. Junkyard Simulator
  6. Train Sim World 6
number:
```

Kein Treffer → Abbruch mit Meldung, ohne irgendetwas zu klicken.

Bequemer Aufruf über das PowerShell-Profil (`$PROFILE`):

```powershell
function wandplay { py d:\Entwicklung\GitHub\Wand-Play\wandplay.py @args }
```

## Als EXE bauen

```powershell
py -m pip install pyinstaller
py build.py
```

Ergebnis: `dist\wandplay.exe`, rund 10,5 MB, eine einzelne Datei ohne Python-Installation
auf dem Zielrechner. Aufruf identisch: `wandplay.exe "Black Flag"`.

Die Versionsnummer steht **ausschließlich** in `__version__` in [wandplay.py](wandplay.py).
[build.py](build.py) erzeugt daraus die Windows-Versionsressource, damit `--version` und die
Dateieigenschaften im Explorer nicht auseinanderlaufen können:

```text
> dist\wandplay.exe --version
wandplay 1.0.0

> (Get-Item dist\wandplay.exe).VersionInfo.FileVersion
1.0.0
```

Für eine neue Version nur `__version__` ändern und `py build.py` erneut ausführen.

## Wie es funktioniert

Wand ist eine Electron-App und über UI Automation vollständig auslesbar. Drei Details,
die nicht offensichtlich sind:

- **Warm-up**: Chromium baut seinen Accessibility-Baum erst, wenn ein UIA-Client danach
  fragt — die erste Antwort ist ein leerer `RootWebArea`. Beim Kaltstart wächst der Baum
  danach noch weiter (Squirrel-Stub → Electron → Login → Spieleliste). Jede Wartestelle
  pollt deshalb auf genau das Element, das sie braucht, statt auf ein schwächeres Signal wie
  „Fenster da" oder „Baum nicht leer". Verschwindet ein Element während eines Re-Renders
  mitten im Durchlauf (`COMError`), wird erneut geschaut, bis der Timeout greift.
- **Spieleliste**: alle Spielzeilen der Sidebar haben dieselbe Größe, das Drumherum
  (Optionen-Buttons, „Alle N Spiele ansehen", aktiver Titel) nicht. Gefiltert wird über die
  häufigste Button-Größe, nicht über feste Pixelwerte — das überlebt Fenstergrößen und
  UI-Sprache. Die Sidebar selbst wird über den Navigationseintrag mit dem Icon-Wort
  `browse` gefunden, sie hat keine ID.
- **Kein Blindklick**: nach dem Klick auf den Listeneintrag steckt der „Spielen"-Button der
  *vorher* geöffneten Seite noch im Baum. Das Tool wartet, bis der Detail-Titel dem
  gewählten Spiel entspricht, und bricht sonst ab, statt das falsche Spiel zu starten.

Geklickt wird über `InvokePattern`, nicht über die Maus: kein Fensterfokus nötig, kein
Mauszeiger-Diebstahl, und Einträge weit unten in der Liste brauchen kein Scrollen.

## Wenn ein Wand-Update die Selektoren bricht

`py wandplay.py --dump` zeigt den kompletten Baum mit Namen, Typ und Geometrie (rund 1300
Zeilen; die Anzahl geht nach stderr, `> baum.txt` bleibt also sauber). Der Dump wartet
bewusst **nicht** auf die Sidebar, sondern darauf, dass der Baum nicht mehr wächst — er muss
ja gerade dann funktionieren, wenn die Selektoren kaputt sind.

Die drei Stellen, die brechen können, stehen in [wandplay.py](wandplay.py): `sidebar()` (der
`browse`-Anker), `sidebar_games()` (Größenfilter) und `PLAY_NAMES` (Beschriftung des
Buttons, aktuell `Spielen`/`Play`).

`PLAY_NAMES` ist die einzige sprachabhängige Stelle — stellst du Wands Oberfläche auf eine
andere Sprache um, muss die dortige Beschriftung ergänzt werden. Anker und Größenfilter sind
sprachunabhängig.

Meldet das Tool *„shows no Play button, only \[…\]"*, ist die Seite korrekt geöffnet und die
Beschriftung passt nur nicht. Steht dort `Spiel hinzufügen`, hat Wand das Spiel nicht mehr
hinzugefügt — einmal in Wand hinzufügen, danach läuft es wieder.

Verifiziert gegen Wand `app-12.45.1`, deutsche Oberfläche.
