# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


project_root = Path(SPEC).resolve().parent


# ============================================================
# Hidden Imports
# ============================================================

hiddenimports: list[str] = []

# Project modules
hiddenimports += collect_submodules(
    "app"
)

# Document libraries
hiddenimports += collect_submodules(
    "pptx"
)

hiddenimports += collect_submodules(
    "openpyxl"
)

hiddenimports += collect_submodules(
    "docx"
)

# Pipelines
hiddenimports += [
    "app.pipeline.pdf_pipeline",
    "app.pipeline.docx_pipeline",
    "app.pipeline.pptx_pipeline",
    "app.pipeline.xlsx_pipeline",
]

# PostgreSQL
hiddenimports += collect_submodules(
    "psycopg"
)


# ============================================================
# Datas / Binaries
# ============================================================

datas = []
binaries = []


def collect_package(
    package_name: str,
) -> None:
    """
    Collect package datas, binaries and hidden imports.
    """

    global datas
    global binaries
    global hiddenimports

    package_datas, package_binaries, package_hiddenimports = (
        collect_all(
            package_name
        )
    )

    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


# ============================================================
# python-pptx
# ============================================================

collect_package(
    "pptx"
)


# ============================================================
# openpyxl
# ============================================================

collect_package(
    "openpyxl"
)


# ============================================================
# python-docx
# ============================================================

collect_package(
    "docx"
)


# ============================================================
# PyMuPDF
# ============================================================

try:
    collect_package(
        "fitz"
    )

except Exception:
    pass


# ============================================================
# psycopg 3
# ============================================================

try:
    collect_package(
        "psycopg"
    )

except Exception:
    pass


# ============================================================
# Application config
# ============================================================

config_file = (
    project_root
    / "config"
    / "config.yaml"
)

if config_file.exists():
    datas.append(
        (
            str(
                config_file
            ),
            "config",
        )
    )


# ============================================================
# Deduplicate hidden imports
# ============================================================

hiddenimports = sorted(
    set(
        hiddenimports
    )
)


# ============================================================
# Analysis
# ============================================================

analysis = Analysis(
    [
        str(
            project_root
            / "app"
            / "gui"
            / "application.py"
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
        # 当前 EXE 不做 Embedding / Qdrant / LLM
        "torch",
        "transformers",
        "sentence_transformers",
        "qdrant_client",

        # 无关开发依赖
        "matplotlib",
        "notebook",
        "IPython",

        # 旧 PostgreSQL driver
        "psycopg2",
    ],
    noarchive=False,
    optimize=0,
)


# ============================================================
# Python Archive
# ============================================================

pyz = PYZ(
    analysis.pure
)


# ============================================================
# OneFile EXE
# ============================================================

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="DocumentIngestion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,

    # GUI application
    console=False,

    disable_windowed_traceback=False,
)