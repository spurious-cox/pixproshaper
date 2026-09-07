"""py2app build for PixProShaper.app

    ~/My_Applications/KBD/venv/bin/python ~/bin/pixpro_make_icon.py \
        PIxProShaperIcon.png --name PixProShaper
    ./venv/bin/python setup.py py2app

Not LSUIElement: unlike the PixPro one-shot applets this is a window you work
in, alongside Pixelmator, so it wants a Dock icon and to be switchable.
"""
import re
from pathlib import Path
from setuptools import setup

APP = ["pixproshaper.py"]


def app_version():
    source = Path(__file__).with_name("pixproshaper.py").read_text()
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if not match:
        raise SystemExit("setup.py: APP_VERSION not found")
    return match.group(1)


VERSION = app_version()

setup(
    name="PixProShaper",
    app=APP,
    options={"py2app": {
        "argv_emulation": False,
        # Built from PIxProShaperIcon.png by ~/bin/pixpro_make_icon.py, which
        # places the artwork on Apple's 824-in-1024 grid so it sits the same
        # size as every other icon in the Dock.
        "iconfile": "PixProShaper.icns",
        # py2app strips bundled binaries by default, and strip mangles some
        # of them badly enough that codesign refuses them outright:
        # "main executable failed strict validation" on liblzma, which could
        # then be neither signed nor un-signed.
        "strip": False,
        # No Pillow here: this app draws nothing. PixProFitText needs it
        # and must carry it as a PACKAGE, because an "include" is compiled
        # into Contents/Resources/lib/python314.zip, and codesign
        # cannot reach inside a zip — so Pillow's 18 bundled dylibs
        # (libbrotli, libfreetype, libjpeg, libwebp, ...) shipped
        # UNSIGNED and Apple rejected the whole archive. A "package"
        # is copied out as a real directory tree, where build.sh's
        # Mach-O walk finds and signs every one of them.
        "includes": ["shaperbridge"],
        "excludes": ["tkinter", "test", "unittest"],
        "plist": {
            "CFBundleName": "PixProShaper",
            "CFBundleDisplayName": "PixProShaper",
            "CFBundleIdentifier": "com.timmccoy.pixproshaper",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright":
                "Copyright © 2026 Tim McCoy. All rights reserved.",
            "CFBundleGetInfoString":
                "PixProShaper — turn selected layers into shapes in "
                "Pixelmator Pro.",
            # It drives Pixelmator Pro over Apple events, so it must say so.
            "NSAppleEventsUsageDescription":
                "PixProShaper reads the selected layers from Pixelmator Pro "
                "and adds the traced shapes back to your document.",
        },
    }},
    setup_requires=["py2app"],
)
