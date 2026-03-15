# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for YouTube MP3/MP4 Downloader

import sys
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'yt_dlp',
        'imageio_ffmpeg',
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
    a.datas,
    [],
    name='YT-Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='YT-Downloader.app',
        bundle_identifier='com.wingsaberrohan.yt-downloader',
        info_plist={
            'CFBundleName': 'YT Downloader',
            'CFBundleDisplayName': 'YouTube MP3/MP4 Downloader',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        },
    )
