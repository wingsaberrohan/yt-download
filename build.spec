# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for YouTube Downloader
# Bundles CustomTkinter data, imageio-ffmpeg binary, and app icon.

import sys
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# ── Collect CustomTkinter theme/font data files ──
ctk_data = collect_data_files('customtkinter')

# ── Locate imageio-ffmpeg's bundled ffmpeg binary ──
ffmpeg_binaries = []
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if ffmpeg_exe and os.path.isfile(ffmpeg_exe):
        ffmpeg_binaries.append((ffmpeg_exe, 'imageio_ffmpeg_bin'))
except Exception:
    print("WARNING: imageio-ffmpeg binary not found; ffmpeg will NOT be bundled.")

# ── Icon path (used at build time for exe metadata + bundled for runtime) ──
icon_file = 'icon.ico' if os.path.isfile('icon.ico') else None
icon_datas = [('icon.ico', '.')] if icon_file else []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=ctk_data + icon_datas,
    hiddenimports=[
        'yt_dlp',
        'imageio_ffmpeg',
        'customtkinter',
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

# ── One-dir build (faster startup, simpler ffmpeg PATH resolution) ──
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YT-Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YT-Downloader',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='YT-Downloader.app',
        bundle_identifier='com.wingsaberrohan.yt-downloader',
        info_plist={
            'CFBundleName': 'YT Downloader',
            'CFBundleDisplayName': 'YouTube Downloader',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
