# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['ade.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['adeversion.py'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    exclude_binaries=True,
    name='ade',
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
    icon=['../resources/MyIcon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ade',
)
app = BUNDLE(
    coll,
    name='ade.app',
    icon='../resources/MyIcon.icns',
    bundle_identifier=None,
    info_plist={
        'CFBundleDocumentTypes': [{
            'CFBundleTypeName': 'Atom Flight Log',
            'CFBundleTypeRole': 'Viewer',
            'LSHandlerRank': 'Owner',
            'CFBundleTypeExtensions': ['fc2'],  # your log file extension
        }],
    },
)
