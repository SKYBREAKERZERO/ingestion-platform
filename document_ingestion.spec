# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


project_root = Path(SPEC).resolve().parent


hiddenimports: list[str] = []

hiddenimports += collect_submodules(
    "app"
)

hiddenimports += collect_submodules(
    "pptx"
)

hiddenimports += collect_submodules(
    "openpyxl"
)

hiddenimports += [
    "app.pipeline.pdf_pipeline",
    "app.pipeline.docx_pipeline",
    "app.pipeline.pptx_pipeline",
    "app.pipeline.xlsx_pipeline",
]


datas = []
binaries = []


# python-pptx
pptx_datas, pptx_binaries, pptx_hiddenimports = (
    collect_all(
        "pptx"
    )
)

datas += pptx_datas
binaries += pptx_binaries
hiddenimports += pptx_hiddenimports


# openpyxl
openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = (
    collect_all(
        "openpyxl"
    )
)

datas += openpyxl_datas
binaries += openpyxl_binaries
hiddenimports += openpyxl_hiddenimports


# PyMuPDF
try:
    fitz_datas, fitz_binaries, fitz_hiddenimports = (
        collect_all(
            "fitz"
        )
    )

    datas += fitz_datas
    binaries += fitz_binaries
    hiddenimports += fitz_hiddenimports

except Exception:
    pass


# python-docx
try:
    docx_datas, docx_binaries, docx_hiddenimports = (
        collect_all(
            "docx"
        )
    )

    datas += docx_datas
    binaries += docx_binaries
    hiddenimports += docx_hiddenimports

except Exception:
    pass


# PostgreSQL driver
try:
    psycopg_datas, psycopg_binaries, psycopg_hiddenimports = (
        collect_all(
            "psycopg"
        )
    )

    datas += psycopg_datas
    binaries += psycopg_binaries
    hiddenimports += psycopg_hiddenimports

except Exception:
    pass


hiddenimports = sorted(
    set(
        hiddenimports
    )
)


analysis = Analysis(
    [
        str(
            project_root
            / "app"
            / "main.py"
        )
    ],
    pathex=[
        str(
            project_root
        )
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "notebook",
        "IPython",
    ],
    noarchive=False,
    optimize=0,
)


pyz = PYZ(
    analysis.pure
)


exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DocumentIngestion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

hiddenimports += collect_submodules(
    "psycopg2"
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DocumentIngestion",
)