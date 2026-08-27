#!/usr/bin/env python
"""Launch a game with Wand's trainer attached, in one command.

    py wandplay.py "Black Flag"   pick the game, let Wand start it
    py wandplay.py --dump         print Wand's accessibility tree (selector debugging)
    py wandplay.py --dump "Black Flag"   open that game's page first, then dump it
    py wandplay.py --selftest     check the name matching
    py wandplay.py --version      print the version

Wand's own "Spielen/Play" button starts the game through Steam and attaches the trainer,
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

# The single source of truth: build.py reads this and stamps it into the exe resource.
__version__ = "1.0.2"

WAND_EXE = Path(os.environ.get("LOCALAPPDATA", "")) / "Wand" / "Wand.exe"

# ponytail: Chromium builds its accessibility tree only once a UIA client asks, and the
# first answer is an empty RootWebArea. A cold start runs Squirrel stub -> Electron -> login
# -> game list, so the tree keeps growing for a while after the window appears; every wait
# below therefore polls for the thing it actually needs instead of trusting one timeout.
TREE_TIMEOUT = 180.0
NAV_TIMEOUT = 25.0
POLL = 0.5

# ponytail: --dump waits for the node count to go quiet. 5 samples 1s apart clears the
# ~2.2s pre-render plateau with margin; shorten only if you re-measure the growth curve.
DUMP_SETTLE = 5
DUMP_POLL = 1.0

# Wand appends material-icon words and badges to accessible names.
ICON_SUFFIXES = (" NEU", " NEW", " kid_star")

# Wand is Aurelia/Chromium, so UIA exposes the CSS classes as ClassName. Anchoring the
# Play button on its component class instead of its label is the one thing that made this
# tool language-dependent. Measured unique in the detail pane; verified in German ("Spielen"),
# Polish ("Graj") and Japanese (katakana), including a non-Latin script.
# ponytail: unverified whether Wand's "add game" state reuses this same component. If it
# does, that state now gets clicked instead of aborted -- harmless (a dialog opens), and the
# state proved unreproducible. Re-add a name check only if it turns out to click wrongly.
PLAY_CLASS = "play-button__main-button"


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


def wait_until(find, timeout, failure):
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
            reason = failure() if callable(failure) else failure
            sys.exit(f"{reason} (gave up after {timeout:.0f}s)")
        time.sleep(POLL)


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
    offered = []  # buttons seen on the title row, so a failure can say what was there

    def find():
        doc = find_web_root(win)
        pane = sidebar(doc) if doc is not None else None
        if pane is None:
            return None
        edge = pane.BoundingRectangle.right
        title = play = None
        buttons = []
        for ctrl, _ in walk(doc):
            r = ctrl.BoundingRectangle
            if r.left <= edge:
                continue  # sidebar shows the name too; only the detail pane counts
            if ctrl.ControlTypeName == "HyperlinkControl" and normalize(ctrl.Name) == game:
                title = ctrl
            elif ctrl.ControlTypeName == "ButtonControl" and ctrl.Name.strip():
                buttons.append((r.top, r.left, ctrl.Name))
                if PLAY_CLASS in ctrl.ClassName.split():
                    play = ctrl
        if title is None:
            return None
        top = title.BoundingRectangle.top
        offered[:] = [n for y, _, n in sorted(buttons) if top <= y <= top + 80]
        return play

    def failure():
        if not offered:
            return f"Wand did not open {game!r}, nothing clicked"
        return (f"Wand opened {game!r} but shows no Play button, only {offered}. "
                f"If it offers to add the game, do that once in Wand. Nothing clicked")

    return wait_until(find, timeout, failure)


# --- entry points ------------------------------------------------------------

def tree_lines(win):
    """The whole web tree as printable lines, or None while it is still empty."""
    doc = find_web_root(win)
    if doc is None:
        return None
    lines = []
    for ctrl, depth in walk(doc):
        r = ctrl.BoundingRectangle
        # Chromium maps the HTML id attribute to AutomationId and the CSS classes to
        # ClassName. Wand's markup carries no ids, so class is the selector-worthy half.
        lines.append(f"{'  ' * depth}{ctrl.ControlTypeName} name={ctrl.Name!r} "
                     f"class={ctrl.ClassName!r} id={ctrl.AutomationId!r} "
                     f"w={r.right - r.left} h={r.bottom - r.top} x={r.left} y={r.top}")
    return lines


def open_game(win, term):
    """Pick the game matching `term` and open its detail page. Returns its name."""
    games = sidebar_games(win)
    game = choose(match_names([n for n, _ in games], term), term)
    invoke(dict(games)[game], f"sidebar entry {game!r}")
    return game


def dump(term=""):
    """Print the tree once it stops growing.

    Waiting for the sidebar instead is not an option: --dump exists for the case where
    those very selectors broke, so the wait has to be selector-free. Node count going
    quiet is that signal -- but a cold start plateaus at ~17 nodes for around two seconds
    before the real render, so the quiet stretch has to outlast that plateau. Measured on
    a cold start: 17 nodes at 6.3s and 6.9s, 1100 at 8.5s, 1326 from 10.2s on.
    """
    win = start_wand()
    if term:
        # No wait_for_detail_page here on purpose: --dump is what you reach for when that
        # very selector broke, and it aborts when it finds no Play button. The settle loop
        # below already waits for the page render to go quiet.
        print(f"--- opened {open_game(win, term)} ---", file=sys.stderr)
    settled, largest, repeats, previous = None, [], 0, -1
    deadline = time.monotonic() + TREE_TIMEOUT
    while time.monotonic() < deadline:
        try:
            lines = tree_lines(win) or []
        except COMError:
            lines = []
        if len(lines) > len(largest):
            largest = lines
        repeats = repeats + 1 if lines and len(lines) == previous else 0
        previous = len(lines)
        if repeats >= DUMP_SETTLE:
            settled = lines
            break
        time.sleep(DUMP_POLL)

    lines = settled if settled is not None else largest
    if not lines:
        sys.exit(f"Wand's accessibility tree stayed empty (gave up after {TREE_TIMEOUT:.0f}s)")
    print("\n".join(lines))
    if settled is None:
        # An idle Wand still wobbles by a node or two, so never settling is possible.
        print("--- never settled, printing the largest sample seen ---", file=sys.stderr)
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
    if argv[0] in ("-V", "--version"):
        return print(f"wandplay {__version__}")
    if argv[0] == "--selftest":
        return selftest()
    if argv[0] == "--dump":
        return dump(" ".join(argv[1:]))

    win = start_wand()
    game = open_game(win, " ".join(argv))
    invoke(wait_for_detail_page(win, game), f"Play button for {game!r}")
    print(f"clicked Play for {game} -- Wand is starting it")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
