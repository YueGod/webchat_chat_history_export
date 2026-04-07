#!/usr/bin/env bash
#
# Build macOS .app bundle and optional .dmg installer
# Usage:
#   ./build_mac.sh          # build .app only
#   ./build_mac.sh --dmg    # build .app + .dmg
#
set -euo pipefail

APP_NAME="微信聊天记录查看器"
BUNDLE_ID="com.wxchathistory.viewer"
VERSION="1.0.0"
ENTRY="main.py"

echo "==> Checking dependencies..."
python3 -c "import webview" 2>/dev/null || {
    echo "pywebview not installed. Run: pip install pywebview"
    exit 1
}
python3 -c "import PyInstaller" 2>/dev/null || {
    echo "PyInstaller not installed. Run: pip install pyinstaller"
    exit 1
}

echo "==> Cleaning previous build..."
rm -rf build dist *.spec

echo "==> Building .app bundle with PyInstaller..."
pyinstaller \
    --windowed \
    --name "${APP_NAME}" \
    --osx-bundle-identifier "${BUNDLE_ID}" \
    --noconfirm \
    --clean \
    --add-data "app:app" \
    "${ENTRY}"

APP_PATH="dist/${APP_NAME}.app"

if [ ! -d "${APP_PATH}" ]; then
    echo "ERROR: .app bundle not found at ${APP_PATH}"
    exit 1
fi

# Update Info.plist with version
PLIST="${APP_PATH}/Contents/Info.plist"
if [ -f "${PLIST}" ]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${PLIST}" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${PLIST}" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true" "${PLIST}" 2>/dev/null || true
fi

echo "==> .app bundle created: ${APP_PATH}"

# Optional DMG creation
if [[ "${1:-}" == "--dmg" ]]; then
    DMG_NAME="${APP_NAME}-${VERSION}.dmg"
    DMG_PATH="dist/${DMG_NAME}"

    echo "==> Creating DMG..."

    STAGING="dist/dmg_staging"
    rm -rf "${STAGING}"
    mkdir -p "${STAGING}"
    cp -R "${APP_PATH}" "${STAGING}/"
    ln -s /Applications "${STAGING}/Applications"

    hdiutil create \
        -volname "${APP_NAME}" \
        -srcfolder "${STAGING}" \
        -ov \
        -format UDZO \
        "${DMG_PATH}"

    rm -rf "${STAGING}"
    echo "==> DMG created: ${DMG_PATH}"
fi

echo "==> Build complete!"
echo ""
echo "To run the app:"
echo "  open \"${APP_PATH}\""
echo ""
echo "To create a DMG installer:"
echo "  ./build_mac.sh --dmg"
