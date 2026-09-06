"""PixProShaper — turn selected layers into shapes in Pixelmator Pro.

A text layer converts directly. An image layer cannot: nothing in
Pixelmator turns pixels into a shape, scripted or not, because that would
be auto-tracing. What it can do is make a SELECTION from the layer's own
content and convert that, which is the same thing by another road — so a
pixel layer is traced by picking out its subject, or a colour, or
everything that is not a colour, and the resulting shape is grouped with
the original, which is hidden and locked as the source it now is.

Everything else — shapes, groups, adjustments, effects, video — is
reported and left alone.

Created by: Claude (Anthropic) for Tim McCoy
"""

APP_VERSION = "1.1.0"
COPYRIGHT = "© 2026 Tim McCoy"

import os
import sys

import objc
from AppKit import (NSApp, NSApplication, NSBackingStoreBuffered, NSButton,
                    NSCenterTextAlignment, NSColor, NSColorWell, NSFont,
                    NSMakeRect, NSMakeSize, NSObject, NSRightTextAlignment,
                    NSScrollView, NSSegmentedControl, NSSlider, NSSwitchButton,
                    NSTextField, NSTextView, NSView, NSViewHeightSizable,
                    NSViewWidthSizable, NSWindow, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
                    NSWindowStyleMaskTitled, NSFocusRingTypeNone, NSAlert,
                    NSBundle, NSWorkspace, NSUserDefaults)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shaperbridge as bridge

WIN_W, WIN_H = 700, 540
METHODS = (("Subject", "subject"), ("Colour", "colour"),
           ("Not colour", "background"))
SETTINGS_KEY = "PixProShaperSettings"

INFO_BODY = (
    "Select layers in Pixelmator Pro, press Reread selection, then Convert.\n\n"

    "TEXT LAYERS convert straight to shapes. Pixelmator renames the layer "
    "to its own text on the way — its doing, not ours.\n\n"

    "PIXEL LAYERS cannot be converted. Nothing in Pixelmator turns pixels "
    "into a shape, scripted or by hand, because that would be auto-tracing "
    "and it has none. What it can do is make a SELECTION from the layer and "
    "convert THAT into a shape, which reaches the same place by another "
    "road. So the whole question is how to choose the selection, and that "
    "is what the three methods are.\n\n"

    "SUBJECT\n"
    "Pixelmator finds the main subject of the layer by itself — the same "
    "machine learning behind Select Subject in its own menus. Smart refine "
    "then tidies the edge, which matters on hair and fur.\n"
    "    Best on: a thing photographed against a background. A person, a "
    "product, an animal.\n"
    "    Poor on: flat graphics, textures, patterns, anything with no "
    "obvious single subject. It will find something, and it may be "
    "nonsense.\n"
    "    Ignores the colour well and tolerance entirely.\n\n"

    "COLOUR\n"
    "Selects everything MATCHING the colour well, within the tolerance, "
    "and traces that.\n"
    "    Best on: artwork with flat colour. Set the well to the ink and you "
    "get the ink.\n"
    "    Tolerance is how far from that colour still counts: 1 is an exact "
    "match, 100 takes in almost anything. Start near 30.\n\n"

    "NOT COLOUR\n"
    "The same selection, inverted: everything that does NOT match. Sample "
    "the background and you are left with the content.\n"
    "    Best on: a subject on a flat, even background where Subject "
    "detection has nothing to grip.\n"
    "    Watch for: if the colour matches nothing, inverting selects the "
    "WHOLE layer and the shape is a rectangle. If it matches everything, "
    "inverting selects nothing and you are told nothing was traced.\n\n"

    "WHICH TO REACH FOR\n"
    "Photograph of a thing: Subject. Flat artwork where you want one "
    "colour: Colour. Flat artwork where you want everything except the "
    "background: Not colour. When one gives a poor edge, the other two cost "
    "nothing to try — undo and convert again.\n\n"

    "WHAT YOU GET\n"
    "The new shape and the original go into a group named for the original, "
    "and the original is hidden and locked. It is the source now, not "
    "something to edit by accident — unlock it if you disagree.\n\n"

    "ANYTHING ELSE is left alone and said so: a shape is already a shape, "
    "and there is no route from a group, adjustment, effect or video layer "
    "to one. Hidden layers are skipped.\n\n"

    "An empty selection converts to nothing and Pixelmator still calls it a "
    "success, so the layers are counted before and after. If a trace found "
    "nothing you are told, rather than left with a group holding one hidden "
    "layer.\n\n"

    "Layers are addressed by their id, not their name. A document with "
    "sixteen layers called \u201cShape\u201d is perfectly normal, and "
    "working by name converts the same one over and over while the rest "
    "appear to have been ignored. The list shows the first characters of "
    "each id so you can tell them apart.\n\n"

    "Only top-level layers are read. A layer inside a group is not seen.")


class FirstMouseButton(NSButton):
    """Acts on the first click even when the window is not key.

    AppKit spends that click activating the window, and NSButton declines
    acceptsFirstMouse — so coming back from Pixelmator, the click that
    should have pressed the button only raised the panel. It reads as a
    control that ignores you at random.
    """

    def acceptsFirstMouse_(self, event):
        return True


class PassthroughLabel(NSTextField):
    """A label that lets clicks reach whatever is behind it.

    A non-editable NSTextField still hit-tests. One laid over a control
    swallows every click on it, which is a long and stupid bug to find.
    """

    def hitTest_(self, point):
        return None


class Flipped(NSView):
    def isFlipped(self):
        return True


def label(text, frame, size=12, weight="reg", colour=None, align=None):
    f = PassthroughLabel.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setEditable_(False)
    f.setSelectable_(False)
    f.setBordered_(False)
    f.setDrawsBackground_(False)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if weight == "bold"
               else NSFont.systemFontOfSize_(size))
    if colour is not None:
        f.setTextColor_(colour)
    if align is not None:
        f.setAlignment_(align)
    return f


def grey(v):
    return NSColor.colorWithCalibratedWhite_alpha_(v, 1.0)


class Controller(NSObject):

    def init(self):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self.bundle = None
        self.rows = []
        self.busy = False
        self.build()
        return self

    # ---------------------------------------------------------------- build
    def build(self):
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIN_W, WIN_H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered, False)
        w.setTitle_("PixProShaper")
        w.setMinSize_(NSMakeSize(640, 460))
        w.setReleasedWhenClosed_(False)
        root = Flipped.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
        w.setContentView_(root)

        # --- the heading: version, name, copyright
        root.addSubview_(label("v" + APP_VERSION, NSMakeRect(14, 12, 90, 18),
                               11.5, "reg", grey(0.45)))
        root.addSubview_(label("PixProShaper", NSMakeRect(0, 9, WIN_W, 22), 15,
                               "bold", None, NSCenterTextAlignment))
        c = label(COPYRIGHT, NSMakeRect(WIN_W - 190, 12, 176, 18), 11.5, "reg",
                  grey(0.45), NSRightTextAlignment)
        c.setAutoresizingMask_(1)                  # pinned to the right edge
        root.addSubview_(c)

        saved = NSUserDefaults.standardUserDefaults().dictionaryForKey_(
            SETTINGS_KEY) or {}

        # --- what is selected
        root.addSubview_(label("Selected layers", NSMakeRect(14, 44, 200, 18),
                               12, "bold"))
        reread = FirstMouseButton.alloc().initWithFrame_(
            NSMakeRect(WIN_W - 150, 40, 136, 26))
        reread.setTitle_("Reread selection")
        reread.setBezelStyle_(1)
        reread.setTarget_(self)
        reread.setAction_("reread:")
        reread.setAutoresizingMask_(1)
        root.addSubview_(reread)
        self.reread_button = reread

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(14, 68, WIN_W - 28, 132))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(2)
        scroll.setAutoresizingMask_(NSViewWidthSizable)
        self.list_view = NSTextView.alloc().initWithFrame_(scroll.bounds())
        self.list_view.setEditable_(False)
        self.list_view.setRichText_(False)
        self.list_view.setFont_(
            NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        scroll.setDocumentView_(self.list_view)
        root.addSubview_(scroll)

        # --- how a pixel layer should be traced
        root.addSubview_(label("Pixel layers are traced by",
                               NSMakeRect(14, 214, 190, 18), 12, "bold"))
        self.method = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(210, 210, 270, 26))
        self.method.setSegmentCount_(len(METHODS))
        for i, (name, _v) in enumerate(METHODS):
            self.method.setLabel_forSegment_(name, i)
            self.method.setWidth_forSegment_(90, i)
        self.method.setSelectedSegment_(int(saved.get("method") or 0))
        self.method.setTarget_(self)
        self.method.setAction_("methodChanged:")
        root.addSubview_(self.method)

        self.refine = FirstMouseButton.alloc().initWithFrame_(
            NSMakeRect(492, 212, 130, 20))
        self.refine.setButtonType_(NSSwitchButton)
        self.refine.setTitle_("Smart refine")
        self.refine.setState_(0 if saved.get("refine") == "0" else 1)
        self.refine.setToolTip_(
            "Let Pixelmator tidy the subject's edge after detecting it.")
        root.addSubview_(self.refine)

        root.addSubview_(label("Colour", NSMakeRect(14, 250, 60, 18)))
        self.well = NSColorWell.alloc().initWithFrame_(
            NSMakeRect(70, 244, 52, 26))
        self.well.setColor_(NSColor.whiteColor())
        # A well that takes first responder opens the system colour picker
        # by itself, which is how the picker ends up in front at launch.
        self.well.setRefusesFirstResponder_(True)
        root.addSubview_(self.well)

        root.addSubview_(label("Tolerance", NSMakeRect(140, 250, 70, 18)))
        self.tolerance = NSSlider.alloc().initWithFrame_(
            NSMakeRect(212, 246, 200, 22))
        self.tolerance.setMinValue_(1)
        self.tolerance.setMaxValue_(100)
        self.tolerance.setDoubleValue_(float(saved.get("tolerance") or 30))
        self.tolerance.setTarget_(self)
        self.tolerance.setAction_("toleranceChanged:")
        root.addSubview_(self.tolerance)
        self.tolerance_read = label("", NSMakeRect(420, 250, 60, 18), 11.5,
                                    "reg", grey(0.35))
        root.addSubview_(self.tolerance_read)

        # --- results
        root.addSubview_(label("Results", NSMakeRect(14, 284, 120, 18), 12,
                               "bold"))
        log_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(14, 308, WIN_W - 28, WIN_H - 308 - 58))
        log_scroll.setHasVerticalScroller_(True)
        log_scroll.setBorderType_(2)
        log_scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.log = NSTextView.alloc().initWithFrame_(log_scroll.bounds())
        self.log.setEditable_(False)
        self.log.setRichText_(False)
        self.log.setFont_(
            NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        log_scroll.setDocumentView_(self.log)
        root.addSubview_(log_scroll)

        # --- the buttons
        for title, action, x, wide in (("Exit", "quit:", 14, 80),
                                       ("Info", "showInfo:", 102, 80)):
            b = FirstMouseButton.alloc().initWithFrame_(
                NSMakeRect(x, WIN_H - 44, wide, 30))
            b.setTitle_(title)
            b.setBezelStyle_(1)
            b.setTarget_(self)
            b.setAction_(action)
            b.setAutoresizingMask_(8)              # pinned to the bottom
            root.addSubview_(b)
        self.convert_button = FirstMouseButton.alloc().initWithFrame_(
            NSMakeRect(WIN_W - 174, WIN_H - 44, 160, 30))
        self.convert_button.setTitle_("Convert to shapes")
        self.convert_button.setBezelStyle_(1)
        self.convert_button.setKeyEquivalent_("\r")
        self.convert_button.setTarget_(self)
        self.convert_button.setAction_("convert:")
        self.convert_button.setAutoresizingMask_(9)
        root.addSubview_(self.convert_button)

        self.status = label("", NSMakeRect(198, WIN_H - 38, WIN_W - 380, 18),
                            11.5, "reg", grey(0.3))
        self.status.setAutoresizingMask_(8 | NSViewWidthSizable)
        root.addSubview_(self.status)

        self.window = w
        self.methodChanged_(None)
        self.toleranceChanged_(None)

    # -------------------------------------------------------------- helpers
    def say_(self, text):
        self.status.setStringValue_(text)

    def note_(self, line):
        self.log.setString_("%s%s\n" % (self.log.string() or "", line))
        self.log.scrollRangeToVisible_((len(self.log.string()), 0))

    def chosen_method(self):
        return METHODS[self.method.selectedSegment()][1]

    def colour_channels(self):
        """The well's colour, in the 0-65535 AppleScript expects.

        Pixelmator's colour channels are NOT 0-255. Passing 255 arrives as
        255 out of 65535 — very nearly black — which has bitten every app
        here that ever set a colour.
        """
        c = self.well.color().colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
        if c is None:
            return (65535, 65535, 65535)
        return tuple(int(round(v * 65535)) for v in
                     (c.redComponent(), c.greenComponent(), c.blueComponent()))

    def save_settings(self):
        NSUserDefaults.standardUserDefaults().setObject_forKey_({
            "method": str(self.method.selectedSegment()),
            "refine": "1" if self.refine.state() else "0",
            "tolerance": str(int(self.tolerance.doubleValue())),
        }, SETTINGS_KEY)

    # -------------------------------------------------------------- actions
    def methodChanged_(self, sender):
        by_colour = self.chosen_method() in ("colour", "background")
        self.refine.setEnabled_(not by_colour)
        self.well.setEnabled_(by_colour)
        self.tolerance.setEnabled_(by_colour)
        self.save_settings()

    def toleranceChanged_(self, sender):
        self.tolerance_read.setStringValue_(
            "%d" % int(self.tolerance.doubleValue()))
        self.save_settings()

    def reread_(self, sender):
        if self.busy:
            return
        self.bundle = bridge.host()
        if self.bundle is None:
            self.list_view.setString_("")
            self.say_("No Pixelmator Pro document is open.")
            return
        try:
            self.rows = bridge.selected_layers(self.bundle)
        except bridge.PixmatorError as exc:
            self.say_(str(exc))
            return
        if not self.rows:
            self.list_view.setString_("")
            self.say_("Nothing selected in Pixelmator.")
            return
        lines = []
        doable = 0
        for r in self.rows:
            if r["kind"] not in bridge.CONVERTIBLE:
                what = "skipped — %s" % r["kind"]
            elif not r["visible"]:
                what = "skipped — hidden"
            else:
                doable += 1
                what = ("text → shape" if r["kind"] == "text layer"
                        else "traced → shape, grouped")
            lines.append("%-30s %-8s %-12s %s"
                         % (r["name"][:30], r["id"][:8],
                            r["kind"].replace(" layer", ""), what))
        self.list_view.setString_("\n".join(lines))
        self.say_("%d of %d layer%s can be converted."
                  % (doable, len(self.rows), "" if len(self.rows) == 1 else "s"))

    def convert_(self, sender):
        if self.busy or not self.rows:
            self.say_("Press Reread selection first.")
            return
        self.busy = True
        self.convert_button.setEnabled_(False)
        self.say_("Converting…")
        self.performSelector_withObject_afterDelay_("_work:", None, 0.05)

    def _work_(self, ignored):
        method = self.chosen_method()
        colour = self.colour_channels()
        tolerance = int(self.tolerance.doubleValue())
        refine = bool(self.refine.state())
        done = 0
        try:
            for r in self.rows:
                name, kind = r["name"], r["kind"]
                if kind not in bridge.CONVERTIBLE:
                    self.note_("%-30s skipped (%s)" % (name, kind))
                    continue
                if not r["visible"]:
                    self.note_("%-30s skipped (hidden)" % name)
                    continue
                try:
                    if kind == "text layer":
                        became = bridge.convert_text(self.bundle, r["id"])
                        self.note_("%-30s → shape “%s”" % (name, became))
                        done += 1
                    else:
                        shape, before, after = bridge.convert_pixels(
                            self.bundle, r["id"], name, method, colour,
                            tolerance, refine)
                        if after <= before - 1 and not shape:
                            # Nothing was made: an empty selection converts
                            # to nothing and still reports success.
                            self.note_("%-30s NOTHING TRACED — the %s "
                                       "selection was empty" % (name, method))
                        else:
                            self.note_("%-30s → shape “%s”, grouped, "
                                       "original hidden and locked"
                                       % (name, shape))
                            done += 1
                except bridge.PixmatorError as exc:
                    self.note_("%-30s FAILED: %s" % (name, exc))
            self.say_("Converted %d layer%s." % (done, "" if done == 1 else "s"))
            self.note_("")
        finally:
            self.busy = False
            self.convert_button.setEnabled_(True)
            self.reread_(None)

    def showInfo_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(1)
        alert.setMessageText_("PixProShaper %s" % APP_VERSION)
        alert.setInformativeText_(INFO_BODY)
        alert.addButtonWithTitle_("OK")
        icon = app_icon()
        if icon is not None:
            alert.setIcon_(icon)
        alert.runModal()

    def quit_(self, sender):
        NSApp.terminate_(None)

    def show(self):
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        self.reread_(None)


def app_icon():
    bundle = NSBundle.mainBundle()
    path = bundle.bundlePath()
    if bundle.bundleIdentifier() != "com.timmccoy.pixproshaper":
        path = "/Applications/PixProShaper.app"
    try:
        return NSWorkspace.sharedWorkspace().iconForFile_(path)
    except Exception:
        return None


class AppDelegate(NSObject):

    def initWithController_(self, controller):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self.controller = controller
        return self

    def applicationDidFinishLaunching_(self, note):
        self.controller.show()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)
    c = Controller.alloc().init()
    d = AppDelegate.alloc().initWithController_(c)
    app.setDelegate_(d)
    app.run()


if __name__ == "__main__":
    main()
