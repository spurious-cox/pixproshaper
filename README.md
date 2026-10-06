# PixProShaper 2.6.0

Turns selected Pixelmator Pro layers into shapes. A text layer converts
directly; a pixel layer is traced from its own outline or from a color,
because nothing in Pixelmator turns pixels into a shape on its own.

### [⬇︎ Download the latest release](https://github.com/spurious-cox/pixproshaper/releases/latest)

Notarized and stapled by Apple — open the DMG and drag PixProShaper to Applications,
or install it with Homebrew:

```
brew install --cask spurious-cox/tap/pixproshaper
```
Requires Pixelmator Pro. Both the 3.x build and the Creator Studio build work;
the app binds to whichever one is in front or has a document open.

## Using it

1. Select the layers to convert in Pixelmator Pro. Only layers at the **top
   level** of the Layers list are read; one inside a group is not seen, so
   drag it out first.
2. Run PixProShaper and choose how a pixel layer should be traced — by its
   **outline**, or by **color**.
3. The resulting shape is grouped with the original, which is hidden as the
   source it now is.

Shapes, groups, adjustments, effects and video are reported and left alone.

## How it works

A text layer has a real conversion command. A pixel layer does not — that would
be auto-tracing — so the app makes a *selection* from the layer's own content
and converts that instead, which reaches the same place by another road. A
black layer is found by selecting black and inverting, since a color-range
selection ignores alpha.

## Building

```
./build.sh
```

The app is signed with a timestamped Developer ID certificate, which keeps
macOS's Automation grant alive across rebuilds, then notarized and stapled.

## Updates

When it opens, PixProShaper asks GitHub whether a newer release exists — at most
once a day, giving up after three seconds — and says nothing if you are up to
date or offline. If there is a newer one, it shows in the status line:

    Update available: X.Y.Z  —  brew upgrade --cask pixproshaper

It only ever reports: nothing is downloaded and nothing replaces itself.

## Problems or suggestions

Open an issue: https://github.com/spurious-cox/pixproshaper/issues

## License

MIT. See [LICENSE](LICENSE).
