# PixProShaper 2.5.2

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

1. Select the layers to convert in Pixelmator Pro.
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

Signing uses a Developer ID certificate selected by SHA-1 hash and timestamped,
which is what keeps macOS's Automation grant alive across rebuilds.
`~/My_Applications/_signing/pixpro_release.sh all <App>` signs and notarizes;
`pixpro_publish.sh <App>` wraps it in the DMG and updates the cask.

## Problems or suggestions

Open an issue: https://github.com/spurious-cox/pixproshaper/issues

## License

MIT. See [LICENSE](LICENSE).
