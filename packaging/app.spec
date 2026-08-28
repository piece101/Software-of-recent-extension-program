# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙.  실행:  pyinstaller packaging/app.spec --noconfirm --clean
# 경로는 이 파일 기준으로 해석되므로 SPECPATH 로 저장소 루트를 계산한다.

import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(SPECPATH)  # noqa: F821  (SPECPATH 는 PyInstaller 가 주입)

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
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden + ["app", "app.gui", "app.core", "app.subtitles"],
    hookspath=[],
    excludes=[
        "torch", "tensorflow", "jax", "matplotlib", "scipy",
        "pandas", "notebook", "IPython", "pytest", "onnx",
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
    icon=os.path.join(ROOT, "assets", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ReclipSubs",
)
