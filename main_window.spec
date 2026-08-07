# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['main_window.py'],
    pathex=[],
    binaries=[],
    datas=[('./res/fonts', 'res/fonts'), ('./res/icons', 'res/icons')],
    hiddenimports=['google.cloud.firestore', 'google.auth'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    onefile=True,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # Exclude binaries from the .exe
    name='main_window',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
