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


def layer_is_black(bundle_id, layer_id):
    """True when every pixel of the layer is black or transparent.

    There is no way to read a pixel from AppleScript, so the layer is asked
    a question it can answer: select everything within a hair of black,
    then invert. What is left is everything that is NOT black. If that
    comes back empty, nothing on the layer is anything but black.

    The inversion is what makes it work. Selecting black directly always
    returns the whole canvas, because a transparent pixel is red 0, green
    0, blue 0 and colour matching ignores transparency — so black artwork
    and empty space give the same answer. Inverting distinguishes them.

    Verified against a layer known to hold no white: asking for white left
    nothing, and inverting that gave the whole canvas back, so an empty
    result really is empty rather than a failed command.
    """
    body = ('set d to front document\n'
            'tell d\n'
            '  deselect\n'
            '  select color range (layer id "%s") color {0, 0, 0} range 2\n'
            '  delay 0.25\n'
            '  invert selection\n'
            '  delay 0.25\n'
            '  set b to selection bounds\n'
            '  deselect\n'
            '  if b is missing value then return "black"\n'
            '  return "mixed"\n'
            'end tell' % _escape(layer_id))
    return run(_tell(bundle_id, body)) == "black"


def convert_pixels(bundle_id, layer_id, name, method,
                   colour=(65535, 65535, 65535), tolerance=50):
    """An image layer gains a shape traced from its own content.

    method is "outline" — the layer's own alpha — or "colour", everything
    matching the given colour within the tolerance.

    The pick is checked before anything is converted. A colour that matches
    NOTHING does not leave an empty selection — Pixelmator selects the
    ENTIRE CANVAS. Measured: after asking for pure black on a layer holding
    none, the selection bounds came back as the whole document. Converting
    that produces a canvas-sized rectangle, which Pixelmator fills black,
    and every layer comes out as a big black box. So the bounds are read
    back and a whole-canvas answer is refused rather than traced.

    Returns (group_name, refusal). `refusal` is None when a shape was made,
    and says why when one was not.

    The check is what the group actually holds, not a layer count. Counting
    top-level layers cannot work here: the new shape adds one, then the
    shape and the original both move into a new group, which removes two
    and adds one. The total is unchanged, so every success read as
    "no layer appeared".
    """
    if method == "outline":
        # The layer's own alpha, which is what "trace this artwork" means.
        # Colour matching cannot do it: a transparent pixel is RGB 0,0,0, so
        # asking for black selects the whole canvas. load selection follows
        # the outline itself, holes and all.
        pick = '  load selection src\n'
    else:
        # Black artwork is hopeless by colour and there is no tolerance that
        # rescues it, so it is caught here rather than after the whole
        # canvas has been traced into a black rectangle.
        if layer_is_black(bundle_id, layer_id):
            return (None, "the artwork is black — colour matching cannot "
                    "tell black from transparency; use Outline")
        pick = ('  select color range src color {%d, %d, %d} range %d\n'
                % (colour[0], colour[1], colour[2], int(tolerance)))

    probe = ('set d to front document\n'
             'tell d\n'
             '  deselect\n'
             '  set src to layer id "%s"\n'
             '%s'
             '  delay 0.3\n'
             '  set b to selection bounds\n'
             '  if b is missing value then return "none"\n'
             '  return ((item 1 of b) as text) & "," & ((item 2 of b) as text)'
             ' & "," & ((item 3 of b) as text) & "," & ((item 4 of b) as text)'
             ' & "," & (width of d as text) & "," & (height of d as text)\n'
             'end tell' % (_escape(layer_id), pick))
    caught = run(_tell(bundle_id, probe))
    if caught == "none":
        return None, "nothing matched — raise the tolerance"
    try:
        x0, y0, x1, y1, dw, dh = [float(v) for v in caught.split(",")]
    except ValueError:
        return None, "the selection could not be read"
    if x0 <= 0 and y0 <= 0 and x1 >= dw and y1 >= dh:
        return (None, "the selection covered the whole canvas — with "
                "Colour that means black on transparency; use Outline")

    body = ('set d to front document\n'
            'tell d\n'
            '  set src to layer id "%s"\n'
            '  set shp to convert selection into shape\n'
            '  delay 0.3\n'
            '  set shapeName to name of shp\n'
            '  set g to make group from {shp, src}\n'
            '  delay 0.3\n'
            '  set name of g to "%s"\n'
            # The reference to src died when the layer moved into the group,
            # but its id did not. Names do not even identify a layer here:
            # this document holds sixteen called "Shape".
            '  set inner to layer id "%s" of g\n'
            '  set visible of inner to false\n'
            '  set locked of inner to true\n'
            '  deselect\n'
            '  return (name of g) & tab & ((count of layers of g) as text)\n'
            'end tell'
            % (_escape(layer_id), _escape("%s (shaped)" % name),
               _escape(layer_id)))
    answer = run(_tell(bundle_id, body))
    parts = answer.split("\t")
    if len(parts) != 2 or parts[1] != "2":
        return None, "the group did not come out right (%s)" % answer
    return parts[0], None
