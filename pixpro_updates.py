"""pixpro_updates — ask GitHub whether a newer release of this app exists.

Read-only by design. It reports the newest published tag and offers to open the
releases page; it never downloads or replaces anything, because a running
bundle cannot safely overwrite its own files and getting that wrong costs the
app.

One copy of this file lives in each PixPro project rather than somewhere
shared: each app ships as a self-contained bundle, and a shared import would be
one more thing that has to exist on the machine it lands on.
"""

import json
import os
import subprocess
import threading
import urllib.request

from AppKit import NSAlert, NSWorkspace
from Foundation import NSURL

API = "https://api.github.com/repos/spurious-cox/%s/releases/latest"
PAGE = "https://github.com/spurious-cox/%s/releases/latest"
TIMEOUT = 10
OPEN_TIMEOUT = 3        # the automatic check at open gives up quickly


def version_tuple(text):
    """"3.4.0" -> (3, 4, 0), so 3.10.0 sorts above 3.9.0 rather than below."""
    parts = []
    for piece in str(text).lstrip("vV").split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def latest_release(slug, version):
    """The newest published tag, or None when GitHub has nothing to say."""
    request = urllib.request.Request(
        API % slug,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "%s/%s" % (slug, version)})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8")).get("tag_name")


def check_for_updates(name, slug, version, icon=None):
    """Compare this build against the newest release and say what it finds."""
    alert = NSAlert.alloc().init()
    alert.setAlertStyle_(1)
    if icon is not None:
        alert.setIcon_(icon)

    try:
        tag = latest_release(slug, version)
    except Exception as exc:
        alert.setMessageText_("Could not check for updates")
        alert.setInformativeText_("GitHub could not be reached.\n\n%s" % exc)
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        return

    if not tag:
        alert.setMessageText_("No releases published yet")
        alert.setInformativeText_("This build is %s." % version)
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        return

    if version_tuple(tag) <= version_tuple(version):
        alert.setMessageText_("%s is up to date" % name)
        alert.setInformativeText_("This build is %s. The newest release is %s."
                                  % (version, tag.lstrip("vV")))
        alert.addButtonWithTitle_("OK")
        alert.runModal()
        return

    alert.setMessageText_("%s is available" % tag.lstrip("vV"))
    alert.setInformativeText_(
        "This build is %s.\n\nOpen the releases page to download it, or update "
        "from the Terminal with:\n    brew upgrade --cask %s" % (version, slug))
    alert.addButtonWithTitle_("Open Releases Page")
    alert.addButtonWithTitle_("Later")
    if alert.runModal() == 1000:
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(PAGE % slug))


def update_line(slug, version):
    """The line every PixPro app shows when a newer release exists, or "".

    Asked at most once a day and cached in ~/.<slug>_defaults, with the same
    keys the applets use, and it gives up after three seconds. Silent when this
    build is current or the network is away.
    """
    domain = os.path.expanduser("~/.%s_defaults" % slug)

    def read(key):
        out = subprocess.run(["/usr/bin/defaults", "read", domain, key],
                             capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else ""

    def write(key, value):
        subprocess.run(["/usr/bin/defaults", "write", domain, key, value],
                       capture_output=True)

    today = __import__("time").strftime("%Y-%m-%d")
    if read("updateCheckedOn") == today:
        tag = read("updateLatestTag")
    else:
        try:
            request = urllib.request.Request(
                API % slug,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "%s/%s" % (slug, version)})
            with urllib.request.urlopen(request,
                                        timeout=OPEN_TIMEOUT) as response:
                tag = json.loads(response.read().decode("utf-8")).get(
                    "tag_name") or ""
        except Exception:
            return ""
        write("updateLatestTag", tag)
        write("updateCheckedOn", today)
    if not tag or version_tuple(tag) <= version_tuple(version):
        return ""
    return "Update available: %s  \u2014  brew upgrade --cask %s" % (
        tag.lstrip("vV"), slug)


def announce(slug, version, deliver):
    """Check once, in the background, when the app opens. `deliver` receives
    the line and must be safe to call from another thread."""
    def work():
        line = update_line(slug, version)
        if line:
            deliver(line)
    threading.Thread(target=work, daemon=True).start()
