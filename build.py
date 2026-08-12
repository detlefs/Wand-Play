#!/usr/bin/env python
"""Build dist/wandplay.exe with the version stamped into it.

    py -m pip install pyinstaller
    py build.py

The version lives in wandplay.py and nowhere else; the Windows version resource is
generated from it here, so `wandplay.exe --version` and the file properties cannot drift.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from wandplay import __version__

HERE = Path(__file__).parent
# Windows version resources are a fixed 4-tuple; "1.0.0" -> (1, 0, 0, 0).
QUAD = tuple(([int(p) for p in __version__.split(".")] + [0, 0, 0, 0])[:4])

VERSION_RESOURCE = f"""\
VSVersionInfo(
  ffi=FixedFileInfo(filevers={QUAD}, prodvers={QUAD}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', "Launch a game with Wand's trainer attached"),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'wandplay'),
      StringStruct('OriginalFilename', 'wandplay.exe'),
      StringStruct('ProductName', 'Wand-Play'),
      StringStruct('ProductVersion', '{__version__}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        resource = Path(tmp) / "version_info.txt"
        resource.write_text(VERSION_RESOURCE, encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--onefile", "--console",
             "--name", "wandplay", "--version-file", str(resource),
             "--clean", "--noconfirm", str(HERE / "wandplay.py")],
            check=True, cwd=HERE)

    exe = HERE / "dist" / "wandplay.exe"
    if not exe.is_file():
        sys.exit("PyInstaller reported success but dist/wandplay.exe is missing")
    print(f"\nbuilt {exe} ({exe.stat().st_size / 1e6:.1f} MB), version {__version__}")


if __name__ == "__main__":
    main()
