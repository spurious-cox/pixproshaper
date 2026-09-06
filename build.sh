#!/bin/zsh
# Build, sign and install PixProShaper.app — v1.0.0
#
# Signing follows the same rules the other apps here learned the hard way:
#
#   * `codesign --deep` is NOT enough for a py2app bundle. It skips the .so
#     files under Resources/lib and the extension-less Mach-O at
#     Contents/MacOS/python, and notarization rejects exactly those. `file`
#     is the only reliable test for what is a Mach-O; filenames are not.
#   * `--options runtime` (hardened runtime) is mandatory for notarization
#     and is not on by default.
#   * The identity is selected by SHA-1 HASH, not by name: expired
#     certificates with similar names are still in the keychain and signing
#     by name can pick a dead one.
#   * --timestamp is not optional; a timestamped signature stays valid after
#     the certificate expires.
#
#   ./build.sh              build and sign into dist/
#   ./build.sh --install    also install to /Applications
set -e
cd "${0:A:h}"

SIGN_ID="4208ABA3EC12F24C1F09C7BB624EFF68B44259DB"

if ! security find-identity -p codesigning | grep -q "$SIGN_ID"; then
    echo "error: signing identity $SIGN_ID not in keychain — see header of this script" >&2
    exit 1
fi

echo "==> stopping any running instance (and its LaunchAgent)"
pkill -x PixProShaper 2>/dev/null || true
sleep 1

echo "==> building"
rm -rf build dist
./venv/bin/python setup.py py2app >/dev/null

# py2app can leave a bundled dylib with rubbish appended past the end of the
# Mach-O — same header, same load commands, ~139KB longer than the original —
# and codesign then refuses it outright ("main executable failed strict
# validation"), so it can be neither signed nor unsigned. Setting strip:False
# does not prevent it. Any dylib that will not sign is replaced with the
# pristine copy from Homebrew, whose install names are identical anyway.
echo "==> repairing any dylib py2app corrupted"
for f in dist/PixProShaper.app/Contents/Frameworks/*.dylib; do
    [[ -f "$f" ]] || continue
    if ! codesign --force --timestamp --options runtime --sign "$SIGN_ID" "$f" 2>/dev/null; then
        base="${f:t}"
        for src in "/opt/homebrew/lib/$base" "/opt/homebrew/opt/${base%%.*}/lib/$base"; do
            if [[ -f "$src" ]]; then
                echo "    replacing $base from $src"
                cp -f "$src" "$f"
                chmod u+w "$f"
                break
            fi
        done
    fi
done

echo "==> signing inner binaries with the hardened runtime"
find dist/PixProShaper.app -type f -print0 2>/dev/null | while IFS= read -r -d $'\0' f; do
    if file -b "$f" 2>/dev/null | grep -q 'Mach-O'; then
        codesign --force --timestamp --options runtime --sign "$SIGN_ID" "$f" 2>/dev/null || true
    fi
done

echo "==> sealing nested frameworks, then the app"
find dist/PixProShaper.app -name '*.framework' -print0 2>/dev/null \
    | xargs -0 -n1 -I{} codesign --force --timestamp --options runtime --sign "$SIGN_ID" {} 2>/dev/null || true
codesign --force --timestamp --options runtime \
    --entitlements pixproshaper.entitlements --sign "$SIGN_ID" dist/PixProShaper.app
codesign --verify --deep --strict dist/PixProShaper.app

if [[ "$1" == "--install" ]]; then
    echo "==> installing to /Applications"
    rm -rf /Applications/PixProShaper.app
    cp -R dist/PixProShaper.app /Applications/
    xattr -dr com.apple.quarantine /Applications/PixProShaper.app 2>/dev/null || true
    codesign -dv /Applications/PixProShaper.app 2>&1 | grep -E "Identifier=|Authority="
    plutil -extract CFBundleShortVersionString raw /Applications/PixProShaper.app/Contents/Info.plist
fi

echo "==> running instances: $(pgrep -x PixProShaper | wc -l | tr -d ' ')"
