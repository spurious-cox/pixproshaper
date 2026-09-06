"""Talk to Pixelmator Pro for PixProShaper.

Every call is one AppleScript round trip, addressed BY BUNDLE ID. The
rebrand means `tell application "Pixelmator Pro"` can reach the Creator
Studio build instead of the one holding the document, and the two keep
separate document lists — so the name is never used.

Created by: Claude (Anthropic) for Tim McCoy
"""

import subprocess

# 3.8 and the Creator Studio rebrand are different apps with different
# document lists. Whichever has a front document is the one to talk to.
BUNDLES = ("com.pixelmatorteam.pixelmator.x", "com.apple.pixelmator")


class PixmatorError(Exception):
    pass


def _escape(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _tell(bundle_id, body):
    return 'tell application id "%s"\n%s\nend tell' % (bundle_id, body)


def run(script):
    done = subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise PixmatorError(done.stderr.strip() or "AppleScript failed")
    return done.stdout.strip()


def host():
    """The Pixelmator holding a document, or None.

    Asked rather than assumed: with both builds installed, guessing wrong
    means every command lands in an app with no document open and fails
    with "Can't get document 1".
    """
    for bundle in BUNDLES:
        try:
            if run(_tell(bundle, 'return (count of documents) as text')) not in ("0", ""):
                return bundle
        except PixmatorError:
            continue
    return None


# Pixelmator reports a layer's class as an AppleScript type; these are the
# only two this app can do anything with. Everything else is reported and
# left alone: a shape is already a shape, and there is no route from a
# group, adjustment, effect or video layer to one.
CONVERTIBLE = ("text layer", "image layer")


def selected_layers(bundle_id):
    """Name, kind and visibility of everything selected, in order."""
    # `selected layers` returns a list whose items will not coerce to a
    # specifier — asking for the name of item 1 fails outright. Filtering
    # every layer on the per-layer `selected` property gives real
    # references, which is what everything downstream needs.
    body = ('set d to front document\n'
            'set out to ""\n'
            'repeat with L in (every layer of d whose selected is true)\n'
            '  set v to "0"\n'
            '  if visible of L then set v to "1"\n'
            '  set out to out & (id of L) & tab & (name of L) & tab & '
            '(class of L as text) & tab & v & linefeed\n'
            'end repeat\n'
            'return out')
    rows = []
    for line in run(_tell(bundle_id, body)).split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append({"id": parts[0], "name": parts[1], "kind": parts[2],
                         "visible": parts[3] == "1"})
    return rows


def _layer_count(bundle_id):
    return int(run(_tell(bundle_id,
                         'return (count of layers of front document) as text')) or 0)


def convert_text(bundle_id, layer_id):
    """A text layer becomes a shape.

    Pixelmator RENAMES the layer to its own text content on the way, so the
    name that goes in is not the name that comes out. The caller is told
    what it ended up as rather than left to guess.
    """
    body = ('set d to front document\n'
            'tell d\n'
            '  set t to layer id "%s"\n'
            '  convert into shape t\n'
            '  delay 0.3\n'
            '  return name of (layer id "%s")\n'
            'end tell' % (_escape(layer_id), _escape(layer_id)))
    return run(_tell(bundle_id, body))


def convert_pixels(bundle_id, layer_id, name, method,
                   colour=(65535, 65535, 65535),
                   tolerance=30, smart_refine=True):
    """An image layer gains a shape traced from its own content.

    method is "subject", "colour" or "background": select the subject, or
    everything matching a colour, or everything that is NOT that colour.

    The new shape and the original go into a group named for the original,
    and the original is hidden and locked — it is the source, not something
    to keep editing by accident.

    An empty selection converts to NOTHING and still reports success, so
    the layers are counted before and after. Silence would mean a group
    holding only a hidden original, which looks like the layer vanished.
    """
    before = _layer_count(bundle_id)
    if method == "subject":
        pick = '  select subject src with smart refine\n' if smart_refine else \
               '  select subject src without smart refine\n'
    else:
        pick = ('  select color range src color {%d, %d, %d} range %d\n'
                % (colour[0], colour[1], colour[2], int(tolerance)))
        if method == "background":
            pick += '  invert selection\n'
    body = ('set d to front document\n'
            'tell d\n'
            '  set src to layer id "%s"\n'
            '%s'
            '  delay 0.3\n'
            '  set shp to convert selection into shape\n'
            '  delay 0.3\n'
            '  set shapeName to name of shp\n'
            '  set g to make group from {shp, src}\n'
            '  delay 0.3\n'
            '  set name of g to "%s"\n'
            # The reference to src died when the layer moved into the group,
            # but its id did not: ids survive the move, names do not even
            # identify it — this document holds sixteen layers called
            # "Shape", and addressing by name converted the same one over
            # and over while the rest looked like they had been ignored.
            '  set inner to layer id "%s" of g\n'
            '  set visible of inner to false\n'
            '  set locked of inner to true\n'
            'end tell\n'
            'return shapeName'
            % (_escape(layer_id), pick, _escape("%s (shaped)" % name),
               _escape(layer_id)))
    shape_name = run(_tell(bundle_id, body))
    after = _layer_count(bundle_id)
    return shape_name, before, after
