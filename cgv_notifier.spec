# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙: 단일 파일(.exe), 콘솔 없는 GUI 앱.

빌드: pyinstaller cgv_notifier.spec
결과: dist/CGV예매알리미.exe
"""

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # keyring이 런타임에 동적 로드하는 Windows 백엔드를 명시적으로 포함
    hiddenimports=[
        'keyring.backends.Windows',
        'keyring.backends.chainer',
        'keyring.backends.fail',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CGV예매알리미',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 콘솔창 숨김 (GUI 전용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
