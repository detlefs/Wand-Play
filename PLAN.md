# Wand-Play — Decision Log

The user manual is in [README.md](README.md). This document records **why** the tool is so
small — in particular which parts of the original plan were dropped outright after the UIA
spike.

Status: 2026-08-12, verified against Wand `app-12.45.1` (German UI), Python 3.14.7,
`uiautomation` 2.0.29.

## The plan was three times as big

Originally the tool was meant to automate five steps: start Wand, read the Steam libraries from
the registry and `libraryfolders.vdf`, find the game via `appmanifest_*.acf`, launch it through
`steam://rungameid/<appid>`, wait for the game process, then click in Wand.

The spike disproved the core assumption: **Wand's "Play" button launches the game itself
through Steam and attaches the trainer.** That makes steps 2–5 pointless. Dropped outright:

| Dropped | Reason |
| --- | --- |
| `winreg` access to `HKCU\SOFTWARE\Valve\Steam` | Steam is never addressed directly |
| parsing `libraryfolders.vdf` with a regex | ditto |
| parsing `appmanifest_*.acf` (`name`/`appid`/`installdir`) | Wand's sidebar **is** the game catalog |
| `os.startfile("steam://rungameid/…")` | Wand launches the game |
| process polling on `<lib>\steamapps\common\<installdir>\` | no readiness signal needed |
| `psutil` resp. `ctypes`/`QueryFullProcessImageName`/`wmic` fallback | see above |

One dependency remains: `uiautomation`.

A side finding that supports this: Wand's sidebar lists 44 titles, the installed Steam library
49 — the difference is non-games (`Steamworks Common Redistributables`, `DSX`,
`s&box editor`) plus `Fallout: London`, which Steam doesn't know at all. The names differ
slightly (`Train Sim World® 6` vs. `Train Sim World 6`), which would have made matching via
Steam names unreliable anyway.

## Confirmed decisions

1. **Location**: script in the repo, not in `%USERPROFILE%`. Convenient invocation via a profile
   function instead of a second copy of the file that drifts apart.
2. **Spike before code**: measure the UIA tree against a running Wand first, then pin the
   selectors down. Worth it — without measuring, warm-up, size filter and the stale-button trap
   would all three have been guessed wrong.
3. **Installed games only**: matching happens exclusively against the sidebar. The carousels on
   the start page also contain titles you don't own (`ELDEN RING`, `Garten of Banban`) and would
   be hit by a substring search.
4. **No blind click**: after clicking the list entry, poll until the detail title matches the
   target game. A `sleep()` would have been a bet here, not a safeguard. This is the one place
   where minimizing was deliberately skipped.
5. **No waiting for game launch**: the tool ends after the "Play" click. Waiting for it would
   have brought back exactly the process polling and `psutil` that were just dropped. That's why
   the success message says "clicked Play", not "game is running".
6. **`--dump` stays**: Wand updates frequently; a tree dump makes broken selectors visible in
   seconds. As a flag in the script, not as a second file.
7. **One self-test**: `--selftest` covers name matching (`normalize`, `match_names`) — the only
   non-trivial pure code. The UIA path can only be checked against a running Wand; that's what
   `--dump` is for.

## Measurements from the spike

- The first UIA access returns an **empty** `RootWebArea` (0 children). Only a further query
  fills it. A retry loop is mandatory, `Exists()` alone is not enough.
- Sidebar game rows are all exactly `226×32` px; options buttons `32×32`, the active-title block
  `234×52`, "View all 11 games" `182×40`. Instead of hard-wiring `226`, the tool filters on the
  **most common** button size — self-calibrating.
- The sidebar has no `AutomationId`. Stable anchor: the navigation entry whose name starts with
  the icon word `browse` plus a space, then two levels up. Levels 2–4 all yield the same pane,
  so there is some slack.
- The sidebar **reorders itself** (most recently played moves to the top). Coordinates are
  worthless, names are the only stable identifier.
- `InvokePattern` is supported by all buttons, even with `IsOffscreen=True`. Hence no `.Click()`:
  no window focus, no pointer hijacking, no scrolling.

## Verification status

Backed by actual execution:

- `--selftest` → `selftest ok`, exit 0
- sidebar extraction → 44 games; `Spielen` and `Optionen für …` correctly filtered out
- multiple hits → `sim` yields 6 titles and the numbered choice
- no hit → `zzz` aborts without clicking
- navigation Black Flag → Starfield → Play button ready after 2.1 s, `invokable=True`
- stale-button protection → asked for `Nightingale` while on a different detail page: refused
  with `Wand did not open 'Nightingale', nothing clicked`, even though a visible "Spielen"
  button was in the tree
- cold start (Wand shut down beforehand), twice → window after 5.9 s, 44 games after 8.3/8.8 s,
  Play button ready after 10.8/11.3 s

## Addendum: two cold-start bugs

On the first real cold start the tool aborted. Two separate causes, both fixed:

1. **`sidebar()` didn't wait at all.** `web_root()` returned as soon as `RootWebArea` had its
   first child — at that point the navigation wasn't rendered yet, and `sidebar()` looked for the
   `browse` anchor exactly once and gave up. A higher timeout would have changed nothing. Now
   every wait polls through a shared `wait_until()` for exactly the element it needs.
2. **`COMError` while walking the tree.** If Wand re-renders during the walk, an element
   disappears and UIA throws. This is treated as "not ready yet" in `wait_until()` and retried;
   the timeout still terminates it.

3. **`--dump` only printed the empty skeleton.** Same root cause as 1: the dump happened as soon
   as `RootWebArea` had one child. Here the fix is deliberately different from the normal path —
   waiting for the sidebar would be wrong, because `--dump` is needed precisely when the
   selectors are broken. The signal has to be selector-free: wait until the tree stops growing
   (two identical node counts in a row). Cold: 1327 lines after 12 s instead of 13 lines
   immediately.

4. **`--dump` fired during the loading screen.** The first version of 3 took "two identical node
   counts in a row" as its signal. The measured growth curve of a cold start, however, shows a
   plateau: 0 nodes at 5.8 s, **17 at 6.3 s and 17 at 6.9 s**, 1100 at 8.5 s, 1326 from 10.2 s
   on. The plateau lasts 2.2 s — the rule landed right in the middle of it and dumped 18 lines.
   Now: 5 identical counts 1 s apart (`DUMP_SETTLE`), which clears the plateau comfortably. The
   curve also shows a permanent jitter at rest (1326 → 1328 → 1326) that strict stability could
   never reach; that's why on timeout the dump prints the largest sample it saw instead of
   failing.

`TREE_TIMEOUT` now sits at 180 s. That is an abort limit, not a wait time — the normal case is
done in ~11 s.

## EXE build and versioning

- **PyInstaller `--onefile`**, driven by [build.py](build.py). Result 10.5 MB, runs without
  Python on the target machine. `comtypes`/UIA work in the freeze without extra flags — checked
  by confirming that `--dump` from the EXE yields the same 1327-line tree as the script.
- **One source for the version**: `__version__` in [wandplay.py](wandplay.py). `build.py`
  generates the Windows version resource (`VSVersionInfo`) from it into a temporary file. The
  alternative would have been maintaining the number in a `.spec` or resource file — two places
  that drift apart. Verified: `--version` says `1.0.0`, `(Get-Item …).VersionInfo.FileVersion`
  says `1.0.0`.
- **No `.spec` in the repo**: `build.py` calls PyInstaller with flags, the generated `.spec` is
  throwaway and listed in [.gitignore](.gitignore).

## Language dependency

During testing Wand was briefly switched to Chinese. That showed the tool's one
language-dependent spot: the Play button, matched by its label (`Spielen`/`Play`).

**Resolved.** Wand is an Aurelia/Chromium app, so UIA exposes each element's CSS classes as
`ClassName`. The Play button is now anchored on `play-button__main-button` — measured unique in
the detail pane, and language-neutral. Verified against Starfield, Black Flag and Avowed, in
three languages: German resolves all three to `name='Spielen'`, Polish to `name='Graj'`,
Japanese to `name='プレイ'` — same class every time, invokable, sidebar unchanged at 44 games.
The old label check would have aborted on the Polish and Japanese runs.

Everything else was already language-neutral: the sidebar anchor (`browse`) is a Material icon
name, the size filter is geometric, and the dump is deliberately selector-free — so it works
precisely when a selector breaks. The one remainder is cosmetic: `ICON_SUFFIXES` still lists the
`NEU`/`NEW` badge words, which only affects display and de-duplication, never a click.

## Wand state, not a tool bug

After the language switch, Wand's detail page for Black Flag offered `Spiel hinzufügen` ("Add
game") instead of `Spielen`; Starfield, Baldur's Gate 3 and Avowed still showed `Spielen`. The
tool correctly aborted instead of clicking. The error message was wrong, though — it said "did
not open" even though the page was open. It now distinguishes both cases and lists the buttons
actually present.

**Open:** the final `Invoke()` on "Spielen" has not yet been run end to end — it launches a real
game. Everything before it has been measured.

## If it should grow after all

Deliberately not built, with the trigger that would justify it:

- **Search via Wand's search field** — needed as soon as a game isn't in the sidebar. Wand's
  search is a button (`search Suchen`), not an `EditControl`; the overlay would have to be
  measured first.
- **Waiting for the game to launch** — needed as soon as something should run after `wandplay` in
  a chain. Brings process polling back.
- **Targeting games that aren't installed** — Wand would offer to install them. Currently
  excluded on purpose (decision 3).
