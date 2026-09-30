#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"

python_path=$(python3 -c 'import sys; assert sys.version_info >= (3, 12); print(sys.executable)')
legacy_database="$project_root/data/personal-os.sqlite3"
app="$project_root/build/Personal OS.app"
sdk="${PERSONAL_OS_MACOS_SDK:-/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk}"
if [ ! -d "$sdk" ]; then
  sdk=$(xcrun --show-sdk-path)
fi

npm run build
mkdir -p "$project_root/build/swift-module-cache"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/runtime/server"
cp -R dist "$app/Contents/Resources/runtime/dist"
cp server/*.py "$app/Contents/Resources/runtime/server/"

swiftc -parse-as-library -swift-version 5 -O \
  -module-cache-path "$project_root/build/swift-module-cache" \
  -sdk "$sdk" -framework AppKit -framework WebKit -framework UserNotifications \
  desktop/PersonalOSApp.swift -o "$app/Contents/MacOS/PersonalOS"

swiftc -parse-as-library -swift-version 5 -O \
  -module-cache-path "$project_root/build/swift-module-cache" \
  -sdk "$sdk" -framework PDFKit \
  desktop/ExtractPDF.swift -o "$project_root/build/PersonalOSPDF"
cp "$project_root/build/PersonalOSPDF" "$app/Contents/Resources/runtime/server/PersonalOSPDF"

swiftc -parse-as-library -swift-version 5 -O \
  -module-cache-path "$project_root/build/swift-module-cache" \
  -sdk "$sdk" -framework AppKit \
  desktop/MakeIcon.swift -o "$project_root/build/make-personal-os-icon"
"$project_root/build/make-personal-os-icon" "$project_root/build/PersonalOS.iconset"
cp "$project_root/build/PersonalOS.iconset/icon_512x512@2x.png" "$app/Contents/Resources/AppIcon.png"

PERSONAL_OS_PLIST_PATH="$app/Contents/Info.plist" \
PERSONAL_OS_PYTHON_PATH="$python_path" \
PERSONAL_OS_LEGACY_PATH="$legacy_database" \
python3 - <<'PY'
import os
import plistlib
from pathlib import Path

with Path('desktop/Info.plist').open('rb') as stream:
    info = plistlib.load(stream)
info['PersonalOSPythonPath'] = os.environ['PERSONAL_OS_PYTHON_PATH']
info['PersonalOSLegacyDataPath'] = os.environ['PERSONAL_OS_LEGACY_PATH']
with Path(os.environ['PERSONAL_OS_PLIST_PATH']).open('wb') as stream:
    plistlib.dump(info, stream)
PY

codesign --force --deep --sign - "$app"
printf '%s\n' "$app"
