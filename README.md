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

`py wandplay.py --dump` zeigt den kompletten Baum mit Namen, Typ und Geometrie. Die drei
Stellen, die brechen können, stehen in [wandplay.py](wandplay.py): `sidebar()` (der
`browse`-Anker), `sidebar_games()` (Größenfilter) und `PLAY_NAMES` (Beschriftung des
Buttons, aktuell `Spielen`/`Play`).

Verifiziert gegen Wand `app-12.45.1`, deutsche Oberfläche.
