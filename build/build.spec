# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# ── Version: single source of truth is src/utils/constants.py:APP_VERSION ────
# This block reads APP_VERSION, then writes version_info.txt (for EXE() below)
# and version.nsh (included by installer.nsi) so no other file needs a version.
_project_root = str(Path(SPECPATH).parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.utils.constants import APP_VERSION as _APP_VERSION  # noqa: E402

_ver_parts = [int(x) for x in _APP_VERSION.split('.')]
while len(_ver_parts) < 4:
    _ver_parts.append(0)
_ver_tuple_str = ', '.join(str(x) for x in _ver_parts)   # e.g. "1, 7, 10, 0"
_ver_str_full  = '.'.join(str(x) for x in _ver_parts)    # e.g. "1.7.10.0"

(Path(SPECPATH) / 'version_info.txt').write_text(
    '# UTF-8\n'
    '#\n'
    '# For more details about fixed file info \'ffi\' see:\n'
    '# http://msdn.microsoft.com/en-us/library/ms646997.aspx\n'
    'VSVersionInfo(\n'
    '  ffi=FixedFileInfo(\n'
    f'    filevers=({_ver_tuple_str}),\n'
    f'    prodvers=({_ver_tuple_str}),\n'
    '    mask=0x3f,\n'
    '    flags=0x0,\n'
    '    OS=0x40004,\n'
    '    fileType=0x1,\n'
    '    subtype=0x0,\n'
    '    date=(0, 0)\n'
    '  ),\n'
    '  kids=[\n'
    '    StringFileInfo(\n'
    '      [\n'
    '        StringTable(\n'
    '          u\'040904B0\',\n'
    '          [\n'
    '            StringStruct(u\'CompanyName\', u\'GaleFling\'),\n'
    '            StringStruct(u\'FileDescription\', u\'GaleFling\'),\n'
    f'            StringStruct(u\'FileVersion\', u\'{_ver_str_full}\'),\n'
    '            StringStruct(u\'InternalName\', u\'GaleFling\'),\n'
    '            StringStruct(u\'OriginalFilename\', u\'GaleFling.exe\'),\n'
    '            StringStruct(u\'ProductName\', u\'GaleFling\'),\n'
    f'            StringStruct(u\'ProductVersion\', u\'{_ver_str_full}\'),\n'
    '          ]\n'
    '        )\n'
    '      ]\n'
    '    ),\n'
    '    VarFileInfo([VarStruct(u\'Translation\', [1033, 1200])])\n'
    '  ]\n'
    ')\n',
    encoding='utf-8',
)

(Path(SPECPATH) / 'version.nsh').write_text(
    f'!define VERSION "{_APP_VERSION}"\n'
    f'!define VERSION_TUPLE "{_ver_str_full}"\n',
    encoding='utf-8',
)
# ─────────────────────────────────────────────────────────────────────────────

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
