# Wand-Play

Launches a game with the [Wand](https://wand.gg) trainer attached, straight from the command
line. Instead of opening Wand, finding the game in the list and clicking "Play":

```text
py wandplay.py "Black Flag"
```

The tool starts Wand (if needed), looks up the title in Wand's game list and clicks "Play".
Wand then launches the game through Steam and attaches the trainer.

## Requirements

- Windows, Python 3.10+ (tested with 3.14.7)
- Wand installed at `%LOCALAPPDATA%\Wand\Wand.exe`
- `py -m pip install -r requirements.txt` (single dependency: `uiautomation`)

Steam does **not** need to be driven separately — Wand takes care of that.

## Usage

```text
py wandplay.py "Black Flag"     partial name, case-insensitive
py wandplay.py --dump           print Wand's accessibility tree
py wandplay.py --selftest       check name matching
py wandplay.py --version        print the version number (also -V)
```

The search term is matched as a substring against Wand's game list. Multiple hits produce a
numbered choice:

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

No hit → abort with a message, without clicking anything.

More convenient invocation via the PowerShell profile (`$PROFILE`):

```powershell
function wandplay { py d:\Entwicklung\GitHub\Wand-Play\wandplay.py @args }
```

## Building an EXE

```powershell
py -m pip install pyinstaller
py build.py
```

Result: `dist\wandplay.exe`, about 10.5 MB, a single file that needs no Python installation on
the target machine. Invocation is identical: `wandplay.exe "Black Flag"`.

The version number lives **exclusively** in `__version__` in [wandplay.py](wandplay.py).
[build.py](build.py) derives the Windows version resource from it, so that `--version` and the
file properties in Explorer cannot drift apart:

```text
> dist\wandplay.exe --version
wandplay 1.0.0

> (Get-Item dist\wandplay.exe).VersionInfo.FileVersion
1.0.0
```

For a new release, just change `__version__` and run `py build.py` again.

## How it works

Wand is an Electron app and fully readable through UI Automation. Three details that are not
obvious:

- **Warm-up**: Chromium only builds its accessibility tree once a UIA client asks for it — the
  first response is an empty `RootWebArea`. On a cold start the tree keeps growing after that
  (Squirrel stub → Electron → login → game list). Every wait therefore polls for exactly the
  element it needs, rather than for a weaker signal like "window is there" or "tree isn't
  empty". If an element disappears during a re-render mid-walk (`COMError`), the walk is
  retried until the timeout hits.
- **Game list**: all game rows in the sidebar share the same size, the surrounding chrome
  (options buttons, "View all N games", the active title) does not. Filtering goes by the most
  common button size, not by hard-coded pixel values — that survives window sizes and UI
  language. The sidebar itself is found via the navigation entry carrying the icon word
  `browse`; it has no ID.
- **No blind click**: after clicking the list entry, the "Play" button of the *previously*
  opened page is still in the tree. The tool waits until the detail title matches the selected
  game, and aborts otherwise instead of launching the wrong game.

Clicking goes through `InvokePattern`, not the mouse: no window focus needed, no pointer
hijacking, and entries far down the list need no scrolling.

## When a Wand update breaks the selectors

`py wandplay.py --dump` prints the complete tree with names, types and geometry (around 1300
lines; the count goes to stderr, so `> tree.txt` stays clean). The dump deliberately does
**not** wait for the sidebar, but for the tree to stop growing — it has to work precisely when
the selectors are broken.

The three places that can break are in [wandplay.py](wandplay.py): `sidebar()` (the `browse`
anchor), `sidebar_games()` (size filter) and `PLAY_NAMES` (the button's label, currently
`Spielen`/`Play`).

`PLAY_NAMES` is the only language-dependent spot — if you switch Wand's UI to another
language, that language's label has to be added. Anchor and size filter are
language-independent.

If the tool reports *"shows no Play button, only \[…\]"*, the page is opened correctly and only
the label doesn't match. If it says `Spiel hinzufügen` ("Add game"), Wand no longer has the
game added — add it once in Wand and it works again.

Verified against Wand `app-12.45.1`, German UI.
