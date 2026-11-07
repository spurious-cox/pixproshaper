#!/bin/zsh
# Notarize PixProShaper.app and wrap it in a distributable DMG — v1.1.0
#
# v1.1.0 also puts a "READ ME FIRST.txt" in the DMG and rewrites the Homebrew
# cask's version and sha256, so brew never serves a DMG the cask no longer
# describes.
#
# Run ./build.sh first; this takes dist/PixProShaper.app as it finds it.
#
# Notarization uses the same keychain profile as Stache, the PixPro apps and
# KBD, so no password lives here or gets typed. If the profile is ever lost:
#   xcrun notarytool store-credentials "PixProNotary" \
#       --apple-id <appleid> --team-id RUDN8D7ZN9
#
# Both the app and the DMG are notarized and stapled. Stapling the app
# matters because that is what gets dragged out of the DMG; stapling the DMG
# matters because that is what gets downloaded. Notarizing only one of the
# two leaves a Gatekeeper warning on the other.
#
# Unlike Stache, this app has NO LaunchAgent — nothing relaunches it — so
# there is no agent to unload around the install, and it must be launched by
# hand afterwards.
set -e
cd "${0:A:h}"

SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"
PROFILE="PixProNotary"
APP="dist/PixProShaper.app"
VOLNAME="PixProShaper"

[[ -d "$APP" ]] || { echo "error: $APP not found — run ./build.sh first" >&2; exit 1; }

VERSION=$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")
DMG="dist/PixProShaper-${VERSION}.dmg"

xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1 \
    || { echo "error: no notary profile '$PROFILE' in keychain" >&2; exit 1; }

echo "==> notarizing the app (PixProShaper $VERSION)"
rm -f dist/PixProShaper_notarize.zip
ditto -c -k --keepParent "$APP" dist/PixProShaper_notarize.zip
xcrun notarytool submit dist/PixProShaper_notarize.zip \
    --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"

echo "==> building the disk image"
rm -rf dist/dmg "$DMG"
mkdir -p dist/dmg
cp -R "$APP" dist/dmg/
ln -s /Applications dist/dmg/Applications
cat > "dist/dmg/READ ME FIRST.txt" <<READMEEOF
PixProShaper $VERSION

WHAT IT IS
    Fits a block of text inside an irregular Pixelmator Pro shape, at the
    largest size that stays inside the outline.

INSTALLING
    Drag PixProShaper onto the Applications folder beside it.

UPDATING
    Quit PixProShaper first if it is running. Unlike Stache it has no login
    agent, so nothing restarts it - but replacing a running app is still
    unreliable.

IT NEEDS PIXELMATOR PRO
    The app does nothing on its own: it drives Pixelmator Pro. The first
    time you use it, macOS asks whether to allow it to control Pixelmator
    Pro, and it cannot work until that is allowed.

    Both Pixelmator Pro 3.x and the Creator Studio build are supported; it
    binds to whichever one has a document open.

USING IT
    Select a shape layer in Pixelmator, type or paste your text, press Try
    to see it, press Apply to place it. The Info button explains what the
    app calculates and what it leaves to you - line height in particular,
    which no script can set and which is the intended finishing touch.

HOMEBREW
    brew install --cask spurious-cox/tap/pixproshaper

https://github.com/spurious-cox/pixproshaper
(c) 2026 Tim McCoy
READMEEOF
# hdiutil intermittently returns "Resource busy" on a folder written seconds
# earlier — something (Spotlight, on-access AV) still has it open. It clears
# on its own, so retry rather than abandoning a build whose app is already
# notarized and stapled.
for attempt in 1 2 3 4 5; do
    if hdiutil create -volname "$VOLNAME" -srcfolder dist/dmg -ov \
            -format UDZO "$DMG" >/dev/null 2>/tmp/pixproshaper_hdiutil.err; then
        break
    fi
    echo "    hdiutil attempt $attempt failed: $(tr -d '\n' < /tmp/pixproshaper_hdiutil.err)"
    if [[ $attempt == 5 ]]; then
        echo "error: could not build the disk image" >&2
        exit 1
    fi
    sleep 5
done
rm -rf dist/dmg

echo "==> signing and notarizing the disk image"
codesign --force --timestamp --sign "$SIGN_ID" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG"

echo "==> installing the stapled app to /Applications"
pkill -x PixProShaper 2>/dev/null || true
sleep 1
rm -rf /Applications/PixProShaper.app
cp -R "$APP" /Applications/
xattr -dr com.apple.quarantine /Applications/PixProShaper.app 2>/dev/null || true

echo "==> updating the Homebrew cask"
TAP="$(brew --repository 2>/dev/null)/Library/Taps/spurious-cox/homebrew-tap"
CASK="$TAP/Casks/pixproshaper.rb"
if [[ -f "$CASK" ]]; then
    SHA=$(shasum -a 256 "$DMG" | cut -d" " -f1)
    # Only the two lines that change per release; rewriting the file from a
    # template would lose the caveats and the zap list.
    /usr/bin/sed -i "" \
        -e "s/^  version \".*\"/  version \"$VERSION\"/" \
        -e "s/^  sha256 \".*\"/  sha256 \"$SHA\"/" "$CASK"
    echo "    $CASK -> $VERSION"
    echo "    sha256 $SHA"
    if brew style --cask "$CASK" >/dev/null 2>&1; then
        echo "    style: ok — commit and push the tap to publish it"
    else
        echo "    style: FAILED — check $CASK by hand" >&2
    fi
else
    echo "    no cask at $CASK — skipped"
fi

echo "==> results"
echo "    dmg:      $DMG  ($(du -h "$DMG" | cut -f1))"
echo "    stapled:  app $(xcrun stapler validate "$APP" >/dev/null 2>&1 && echo YES || echo no), dmg $(xcrun stapler validate "$DMG" >/dev/null 2>&1 && echo YES || echo no)"
spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 | sed 's/^/    gatekeeper: /'
echo "    running instances: $(pgrep -x PixProShaper | wc -l | tr -d ' ')  (no LaunchAgent — relaunch by hand)"
