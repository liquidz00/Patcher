#!/bin/bash
# Build script for patcher

set -e

# Parse sensitive arguments
APPLE_ID=$1
TEAM_ID=$2
APP_SPECIFIC_PASSWORD=$3
CERT_NAME=$4
INSTALLER_CERT_NAME=$5
P12_PASSWORD=$6

# Variables
APP_NAME="Patcher"
APP_PY="patcher.py"
OUTPUT_DIR="dist"
BINARY_PATH="$OUTPUT_DIR/$APP_NAME"
PKG_NAME="$APP_NAME.pkg"
TMP_PKG_NAME="tmp_$PKG_NAME"
INSTALL_PATH="/usr/local/bin"
ENTITLEMENTS="$(pwd)/entitlements.plist"

# Ensure script is run from the correct directory
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR/../../"

# Create binary using PyInstaller
pyinstaller --onefile --clean --osx-bundle-identifier com.liquidzoo.$APP_NAME $APP_PY

# Ensure binary has proper permissions
chmod +x $BINARY_PATH

# Import certificates
security import "$CERT_NAME" -k ~/Library/Keychains/login.keychain-db -P "$P12_PASSWORD" -T /usr/bin/codesign
security import "$INSTALLER_CERT_NAME" -k ~/Library/Keychains/login.keychain-db -P "$P12_PASSWORD" -T /usr/bin/productsign

# Sign the binary with hardened runtime and entitlements
codesign --deep --force --verbose --options=runtime --entitlements "$ENTITLEMENTS" --timestamp --sign "$CERT_NAME" "$BINARY_PATH"

# Verify the binary signing
codesign --verify --deep --strict --verbose=2 "$BINARY_PATH"

# Create scripts directory
if [ ! -d "scripts" ]; then mkdir scripts; fi

# Create .pkg installer
pkgbuild --root $OUTPUT_DIR --identifier com.liquidzoo.$APP_NAME --install-location $INSTALL_PATH --scripts scripts $PKG_NAME

# Unlock keychain to access cert
security unlock-keychain -p "$KEYCHAIN_PASSWORD_SECRET" ~/Library/Keychains/login.keychain-db

# Sign the package
productsign --sign "$INSTALLER_CERT_NAME" $PKG_NAME $TMP_PKG_NAME

# Rename the PKG
mv $TMP_PKG_NAME $PKG_NAME

# Notarize the package
echo "Submitting $PKG_NAME for notarization..."
NOTARIZATION_OUTPUT=$(xcrun notarytool submit "$PKG_NAME" --apple-id "$APPLE_ID" --team-id "$TEAM_ID" --password "$APP_SPECIFIC_PASSWORD" --wait)

# Check notarization status
if echo "$NOTARIZATION_OUTPUT" | grep -q "status: Accepted"; then
	echo "Notarization successful."
else
	# Retrieve notarization log, submission failed
	NOTARIZATION_ID=$(echo "$NOTARIZATION_OUTPUT" | grep -m 1 "id:" | awk '{print $2}')
	echo "Notarization failed. Retrieving log..."
	xcrun notarytool log "$NOTARIZATION_ID" --apple-id "$APPLE_ID" --team-id "$TEAM_ID" --password "$APP_SPECIFIC_PASSWORD"
	exit 1
fi

# Staple the notarization ticket to the package
xcrun stapler staple "$PKG_NAME"

echo "Build, signing, and notarization complete. The signed and notarized package is $PKG_NAME"
