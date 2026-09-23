# Bundled Python signature

## Signals and mechanism

After launching the macOS client, `codesign --verify --deep --strict` failed although signing passed immediately after the build. Python had written `__pycache__` files inside `Contents/Resources/runtime/server/`, changing the signed bundle on first use.

## Handling and limits

Set `PYTHONDONTWRITEBYTECODE=1` in the child process environment before launching the bundled server. Keep its writable database, ready file, and log under Application Support, outside the app bundle. This applies when Python source is packaged as resources and run from inside a signed `.app`; it does not establish a general distribution or notarization policy.

## Evidence and verification

The startup environment is set in [`desktop/PersonalOSApp.swift`](../../../desktop/PersonalOSApp.swift). After building with [`scripts/build-macos-app.sh`](../../../scripts/build-macos-app.sh), launching the native app and using Settings, `codesign --verify --deep --strict --verbose=2 'build/Personal OS.app'` passed and `find 'build/Personal OS.app' -name '__pycache__' -o -name '*.pyc'` returned no files. Verified once on 2026-09-23.
