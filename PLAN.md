# Wand-Play — Entscheidungsprotokoll

Bedienungsanleitung steht in [README.md](README.md). Dieses Dokument hält fest, **warum**
das Tool so klein ist — insbesondere, welche Teile des ursprünglichen Plans nach dem
UIA-Spike ersatzlos gestrichen wurden.

Stand: 2026-08-12, verifiziert gegen Wand `app-12.45.1` (deutsche Oberfläche),
Python 3.14.7, `uiautomation` 2.0.29.

## Der Plan war dreimal so groß

Ursprünglich sollte das Tool fünf Schritte automatisieren: Wand starten, Steam-Bibliotheken
aus Registry und `libraryfolders.vdf` einlesen, Spiel per `appmanifest_*.acf` finden, über
`steam://rungameid/<appid>` starten, auf den Spielprozess warten, dann in Wand klicken.

Der Spike hat die Grundannahme widerlegt: **Wands „Spielen"-Button startet das Spiel selbst
über Steam und hängt den Trainer an.** Damit sind die Schritte 2–5 überflüssig. Ersatzlos
gestrichen:

| Gestrichen | Grund |
| --- | --- |
| `winreg`-Zugriff auf `HKCU\SOFTWARE\Valve\Steam` | Steam wird nie direkt angesprochen |
| `libraryfolders.vdf` per Regex parsen | dito |
| `appmanifest_*.acf` parsen (`name`/`appid`/`installdir`) | Wands Sidebar **ist** der Spielekatalog |
| `os.startfile("steam://rungameid/…")` | Wand startet das Spiel |
| Prozess-Polling auf `<lib>\steamapps\common\<installdir>\` | kein Bereitschaftssignal nötig |
| `psutil` bzw. `ctypes`/`QueryFullProcessImageName`/`wmic`-Fallback | siehe oben |

Übrig bleibt eine Abhängigkeit: `uiautomation`.

Nebenbefund, der das stützt: Wands Sidebar listet 44 Titel, die installierte Steam-Bibliothek
49 — die Differenz sind Nicht-Spiele (`Steamworks Common Redistributables`, `DSX`,
`s&box editor`) plus `Fallout: London`, das Steam gar nicht kennt. Die Namen weichen leicht
ab (`Train Sim World® 6` vs. `Train Sim World 6`), was ein Matching über Steam-Namen ohnehin
unzuverlässig gemacht hätte.

## Bestätigte Entscheidungen

1. **Ablageort**: Skript im Repo, nicht in `%USERPROFILE%`. Bequemer Aufruf über eine
   Profil-Funktion statt einer zweiten Dateikopie, die auseinanderdriftet.
2. **Spike vor Code**: UIA-Baum erst am laufenden Wand vermessen, dann Selektoren fixieren.
   Hat sich gelohnt — ohne Messung wären Warm-up, Größenfilter und die Stale-Button-Falle
   alle drei falsch geraten worden.
3. **Nur installierte Spiele**: Gematcht wird ausschließlich gegen die Sidebar. Die
   Karussells der Startseite enthalten auch nicht besessene Titel (`ELDEN RING`,
   `Garten of Banban`) und würden bei Teilstring-Suche mittreffen.
4. **Kein Blindklick**: Nach dem Klick auf den Listeneintrag wird gepollt, bis der
   Detail-Titel dem Zielspiel entspricht. Ein `sleep()` wäre hier eine Wette gewesen, kein
   Schutz. Das ist die eine Stelle, an der bewusst nicht minimiert wurde.
5. **Kein Warten auf den Spielstart**: Nach dem „Spielen"-Klick endet das Tool. Darauf zu
   warten hätte das gerade gestrichene Prozess-Polling samt `psutil` zurückgeholt. Die
   Erfolgsmeldung sagt deshalb „Play geklickt", nicht „Spiel läuft".
6. **`--dump` bleibt**: Wand aktualisiert sich häufig; ein Baum-Dump macht kaputte
   Selektoren in Sekunden sichtbar. Als Flag im Skript, nicht als zweite Datei.
7. **Ein Selbsttest**: `--selftest` deckt das Namens-Matching ab (`normalize`,
   `match_names`) — der einzige nicht-triviale reine Code. Der UIA-Pfad ist nur am
   laufenden Wand prüfbar; dafür ist `--dump` da.

## Messergebnisse aus dem Spike

- Der erste UIA-Zugriff liefert einen **leeren** `RootWebArea` (0 Kinder). Erst eine weitere
  Abfrage füllt ihn. Eine Retry-Schleife ist zwingend, `Exists()` allein reicht nicht.
- Spielzeilen der Sidebar haben alle exakt `226×32` px; Optionen-Buttons `32×32`, der
  aktive-Titel-Block `234×52`, „Alle 11 Spiele ansehen" `182×40`. Statt `226` zu verdrahten,
  filtert das Tool auf die **häufigste** Button-Größe — selbstkalibrierend.
- Die Sidebar hat keine `AutomationId`. Stabiler Anker: der Navigationseintrag, dessen Name
  mit dem Icon-Wort `browse` plus Leerzeichen beginnt, dann zwei Ebenen nach oben. Die Ebenen 2–4 liefern
  alle dieselbe Pane, es gibt also Spielraum.
- Die Sidebar **sortiert sich um** (zuletzt gespielt wandert nach oben). Koordinaten sind
  wertlos, Namen sind die einzige stabile Kennung.
- `InvokePattern` wird von allen Buttons unterstützt, auch bei `IsOffscreen=True`. Deshalb
  kein `.Click()`: kein Fensterfokus, kein Mauszeiger-Diebstahl, kein Scrollen.

## Verifikationsstand

Belegt durch Ausführung:

- `--selftest` → `selftest ok`, exit 0
- Sidebar-Extraktion → 44 Spiele; `Spielen` und `Optionen für …` korrekt herausgefiltert
- Mehrfachtreffer → `sim` liefert 6 Titel und die nummerierte Auswahl
- Kein Treffer → `zzz` bricht ab, ohne zu klicken
- Navigation Black Flag → Starfield → Play-Button nach 2,1 s bereit, `invokable=True`
- Stale-Button-Schutz → auf einer fremden Detailseite nach `Nightingale` gefragt: verweigert
  mit `Wand did not open 'Nightingale', nothing clicked`, obwohl ein sichtbarer
  „Spielen"-Button im Baum lag
- Kaltstart (Wand vorher beendet), zweimal → Fenster nach 5,9 s, 44 Spiele nach 8,3/8,8 s,
  Play-Button bereit nach 10,8/11,3 s

## Nachtrag: zwei Kaltstart-Bugs

Beim ersten echten Kaltstart brach das Tool ab. Zwei getrennte Ursachen, beide gefixt:

1. **`sidebar()` wartete gar nicht.** `web_root()` kehrte zurück, sobald `RootWebArea` sein
   erstes Kind hatte — da war die Navigation noch nicht gerendert, und `sidebar()` suchte den
   `browse`-Anker genau einmal und brach ab. Ein höherer Timeout hätte daran nichts geändert.
   Jetzt pollt jede Wartestelle über einen gemeinsamen `wait_until()` auf genau das Element,
   das sie braucht.
2. **`COMError` beim Baum-Durchlauf.** Rendert Wand während des Walks neu, verschwindet ein
   Element und UIA wirft. Wird in `wait_until()` als „noch nicht fertig" behandelt und erneut
   versucht; der Timeout beendet es weiterhin.

`TREE_TIMEOUT` steht jetzt bei 180 s. Das ist eine Abbruchgrenze, keine Wartezeit — der
Normalfall ist in ~11 s durch.

**Offen:** Der finale `Invoke()` auf „Spielen" ist noch nicht End-to-End ausgeführt worden —
er startet ein echtes Spiel. Alles davor ist gemessen.

## Wenn es doch mehr werden soll

Bewusst nicht gebaut, mit Auslöser:

- **Suche über Wands Suchfeld** — nötig, sobald ein Spiel nicht in der Sidebar steht. Wands
  Suche ist ein Button (`search Suchen`), kein `EditControl`; das Overlay wäre erst zu
  vermessen.
- **Warten auf den Spielstart** — nötig, sobald etwas nach `wandplay` in einer Kette laufen
  soll. Bringt Prozess-Polling zurück.
- **Nicht installierte Spiele ansteuern** — Wand würde die Installation anbieten. Aktuell
  bewusst ausgeschlossen (Entscheidung 3).
