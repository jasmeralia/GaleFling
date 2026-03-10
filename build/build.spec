# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

py_dll_name = f'python{sys.version_info.major}{sys.version_info.minor}.dll'
py_dll_path = Path(sys.base_prefix) / py_dll_name
binaries = []
if py_dll_path.exists():
    binaries.append((str(py_dll_path), '.'))

# Bundle ffmpeg binary from imageio-ffmpeg
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    binaries.append((ffmpeg_exe, 'imageio_ffmpeg/binaries'))
except ImportError:
    pass

block_cipher = None

a = Analysis(
    ['../src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=[
        ('../resources/default_config.json', 'resources'),
        ('../resources/icon.ico', 'resources'),
        ('../resources/icon.png', 'resources'),
    ],
    hiddenimports=[
        'keyring.backends.Windows',
        'PIL',
        'tweepy',
        'atproto',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'imageio_ffmpeg',
        'ffmpeg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GaleFling',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../resources/icon.ico',
    version='version_info.txt',
)
