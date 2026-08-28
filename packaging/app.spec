# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 — 저장소 루트에서 실행:  pyinstaller packaging/app.spec --noconfirm --clean

from PyInstaller.utils.hooks import collect_all

_datas, _binaries, _hidden = [], [], []
for _pkg in (
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "tokenizers",
    "huggingface_hub",
    "certifi",
):
    d, b, h = collect_all(_pkg)
    _datas += d
    _binaries += b
    _hidden += h

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden + ["app", "app.gui", "app.core", "app.subtitles"],
    hookspath=[],
    excludes=[
        "torch", "tensorflow", "jax", "matplotlib", "scipy",
        "pandas", "notebook", "IPython", "pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReclipSubs",
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ReclipSubs",
)
