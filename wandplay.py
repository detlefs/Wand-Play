#!/usr/bin/env python
"""Launch a game with Wand's trainer attached, in one command.

    py wandplay.py "Black Flag"   pick the game, let Wand start it
    py wandplay.py --dump         print Wand's accessibility tree (selector debugging)
    py wandplay.py --selftest     check the name matching

Wand's own "Spielen" button starts the game through Steam and attaches the trainer,
so this drives Wand only -- no Steam registry, manifests or process polling needed.
"""
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import uiautomation as auto
from comtypes import COMError

WAND_EXE = Path(os.environ.get("LOCALAPPDATA", "")) / "Wand" / "Wand.exe"

# ponytail: Chromium builds its accessibility tree only once a UIA client asks, and the
# first answer is an empty RootWebArea. A cold start runs Squirrel stub -> Electron -> login
# -> game list, so the tree keeps growing for a while after the window appears; every wait
# below therefore polls for the thing it actually needs instead of trusting one timeout.
TREE_TIMEOUT = 180.0
NAV_TIMEOUT = 25.0
POLL = 0.5

# Wand appends material-icon words and badges to accessible names.
ICON_SUFFIXES = (" NEU", " NEW", " kid_star")
PLAY_NAMES = {"spielen", "play"}


# --- pure helpers (covered by --selftest) ------------------------------------

def normalize(name):
    """Strip Wand's badge/icon suffixes from an accessible name."""
    n = name.strip()
    while True:
        for suffix in ICON_SUFFIXES:
            if n.endswith(suffix):
                n = n[: -len(suffix)].strip()
                break
        else:
            return n


def match_names(names, term):
    """Case-insensitive substring matches, order-preserving and deduplicated."""
    needle = term.casefold()
    hits = []
    for name in names:
        if needle in name.casefold() and name not in hits:
            hits.append(name)
    return hits


# --- UI access ---------------------------------------------------------------

def walk(root, max_depth=25):
    return auto.WalkControl(root, includeTop=False, maxDepth=max_depth)


def start_wand():
    """Return Wand's main window, starting Wand if it isn't showing one."""
    win = auto.WindowControl(searchDepth=1, Name="Wand")
    if win.Exists(2, 1):
        return win
    if not WAND_EXE.is_file():
        sys.exit(f"Wand not found at {WAND_EXE}")
    subprocess.Popen([str(WAND_EXE)])
    if not win.Exists(TREE_TIMEOUT, 1):
        sys.exit(f"Wand window did not appear within {TREE_TIMEOUT:.0f}s")
    return win


def wait_until(find, timeout, failure, poll=POLL):
    """Poll `find` until it returns something truthy, else give up with a message.

    Every readiness check waits on the element it actually needs. Waiting on a weaker
    signal (the window, or a non-empty tree) returns while Wand is still rendering.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            found = find()
        except COMError:
            # An element vanished mid-walk because Wand re-rendered. Not an error while
            # we are waiting for that very render -- look again. The deadline still ends it.
            found = None
        if found:
            return found
        if time.monotonic() >= deadline:
            sys.exit(f"{failure} (gave up after {timeout:.0f}s)")
        time.sleep(poll)


def find_web_root(win):
    """Chromium's populated renderer tree, or None while it is still empty."""
    for ctrl, _ in walk(win, max_depth=14):
        if ctrl.ControlTypeName == "DocumentControl" and ctrl.AutomationId == "RootWebArea":
            return ctrl if ctrl.GetChildren() else None
    return None


def sidebar(doc):
    """The game-list pane, or None while Wand has not rendered its nav yet.

    Anchored on the nav entry whose icon word is 'browse', two levels up. Levels 2-4 all
    resolve to the same pane, so there is slack before a Wand markup change breaks it.
    """
    for ctrl, _ in walk(doc):
        if ctrl.ControlTypeName == "HyperlinkControl" and ctrl.Name.startswith("browse "):
            return ctrl.GetParentControl().GetParentControl()
    return None


def sidebar_games(win, timeout=TREE_TIMEOUT):
    """Installed games from the sidebar, as [(display name, control)].

    Every game row shares one exact size; the options buttons, the active-game header
    and the "show all" link do not. Taking the most common size self-calibrates instead
    of hardcoding pixels, which survives window resizes and UI language changes.
    """
    def find():
        doc = find_web_root(win)
        pane = sidebar(doc) if doc is not None else None
        if pane is None:
            return None
        buttons = []
        for ctrl, _ in walk(pane):
            if ctrl.ControlTypeName != "ButtonControl" or not ctrl.Name.strip():
                continue
            r = ctrl.BoundingRectangle
            buttons.append(((r.right - r.left, r.bottom - r.top), ctrl))
        if not buttons:
            return None

        row_size, _ = Counter(size for size, _ in buttons).most_common(1)[0]
        games, seen = [], set()
        for size, ctrl in buttons:
            name = normalize(ctrl.Name)
            if size == row_size and name not in seen:
                seen.add(name)
                games.append((name, ctrl))
        return games

    return wait_until(find, timeout, "Wand's game list never appeared -- run --dump")


def invoke(ctrl, what):
    """Click without moving the mouse or raising the window."""
    pattern = ctrl.GetInvokePattern()
    if pattern is None:
        sys.exit(f"{what} cannot be invoked -- run --dump")
    pattern.Invoke()


def choose(hits, term):
    if not hits:
        sys.exit(f"no installed game matches {term!r}")
    if len(hits) == 1:
        return hits[0]
    print(f"{len(hits)} matches for {term!r}:")
    for i, name in enumerate(hits, 1):
        print(f"  {i}. {name}")
    try:
        answer = input("number: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")
    if not answer.isdigit() or not 1 <= int(answer) <= len(hits):
        sys.exit(f"not a valid choice: {answer!r}")
    return hits[int(answer) - 1]


def wait_for_detail_page(win, game, timeout=NAV_TIMEOUT):
    """Return the Play button, but only once the page really shows `game`.

    Without this the stale Play button of the previously open game is still in the
    tree, and a naive search would start the wrong game.
    """
    def find():
        doc = find_web_root(win)
        pane = sidebar(doc) if doc is not None else None
        if pane is None:
            return None
        edge = pane.BoundingRectangle.right
        title = play = None
        for ctrl, _ in walk(doc):
            if ctrl.BoundingRectangle.left <= edge:
                continue  # sidebar shows the name too; only the detail pane counts
            if ctrl.ControlTypeName == "HyperlinkControl" and normalize(ctrl.Name) == game:
                title = ctrl
            elif ctrl.ControlTypeName == "ButtonControl" and ctrl.Name.casefold() in PLAY_NAMES:
                play = ctrl
        return play if title is not None else None

    return wait_until(find, timeout, f"Wand did not open {game!r}, nothing clicked")


# --- entry points ------------------------------------------------------------

def tree_lines(win):
    """The whole web tree as printable lines, or None while it is still empty."""
    doc = find_web_root(win)
    if doc is None:
        return None
    lines = []
    for ctrl, depth in walk(doc):
        r = ctrl.BoundingRectangle
        lines.append(f"{'  ' * depth}{ctrl.ControlTypeName} name={ctrl.Name!r} "
                     f"id={ctrl.AutomationId!r} w={r.right - r.left} h={r.bottom - r.top} "
                     f"x={r.left} y={r.top}")
    return lines


def dump():
    """Print the tree once it stops growing.

    Chromium keeps filling the tree for seconds after the first node appears, so dumping
    on that signal prints a near-empty shell. Waiting for the sidebar instead is not an
    option: --dump exists for the case where those very selectors broke, so the wait has
    to be selector-free. Two identical node counts in a row is that signal.
    """
    win = start_wand()
    previous = [-1]

    def settled():
        lines = tree_lines(win) or []
        stable = len(lines) > 0 and len(lines) == previous[0]
        previous[0] = len(lines)
        return lines if stable else None

    lines = wait_until(settled, TREE_TIMEOUT, "Wand's tree never stopped changing", poll=1.0)
    print("\n".join(lines))
    print(f"--- {len(lines)} controls ---", file=sys.stderr)


def selftest():
    assert normalize("Soulmask NEU") == "Soulmask"
    assert normalize("Baldur's Gate 3 kid_star") == "Baldur's Gate 3"
    assert normalize("PowerWash Simulator 2 NEU") == "PowerWash Simulator 2"
    assert normalize("Universe Sandbox ²") == "Universe Sandbox ²"

    names = [normalize(n) for n in [
        "Assassin's Creed Black Flag Resynced", "Baldur's Gate 3 kid_star",
        "Baldur's Gate 3", "Starfield", "FOUNDRY", "FOUNDRY: Mod Kit",
        "Train Sim World 6", "Soulmask NEU",
    ]]
    assert match_names(names, "black flag") == ["Assassin's Creed Black Flag Resynced"]
    assert match_names(names, "BLACK FLAG") == ["Assassin's Creed Black Flag Resynced"]
    assert match_names(names, "gate") == ["Baldur's Gate 3"], "badge duplicate not merged"
    assert match_names(names, "foundry") == ["FOUNDRY", "FOUNDRY: Mod Kit"], "substring of another title dropped"
    assert match_names(names, "soulmask") == ["Soulmask"]
    assert match_names(names, "nope") == []
    print("selftest ok")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.exit(__doc__.strip())
    if argv[0] == "--selftest":
        return selftest()
    if argv[0] == "--dump":
        return dump()

    term = " ".join(argv)
    win = start_wand()
    games = sidebar_games(win)
    game = choose(match_names([n for n, _ in games], term), term)
    invoke(dict(games)[game], f"sidebar entry {game!r}")
    invoke(wait_for_detail_page(win, game), f"Play button for {game!r}")
    print(f"clicked Play for {game} -- Wand is starting it")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
