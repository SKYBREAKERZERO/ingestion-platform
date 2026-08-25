# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


# ============================================================
# Project
# ============================================================

project_root = Path(SPEC).resolve().parent

entry_script = (
    project_root
    / "app"
    / "gui"
    / "application.py"
)


# ============================================================
# Collections
# ============================================================

hiddenimports: list[str] = []
datas = []
binaries = []


# ============================================================
# Helper Functions
# ============================================================

def collect_package(
    package_name: str,
) -> None:
    """
    Collect a package completely.

    Includes:
        - data files
        - binary files
        - hidden imports
    """

    global datas
    global binaries
    global hiddenimports

    (
        package_datas,
        package_binaries,
        package_hiddenimports,
    ) = collect_all(
        package_name
    )

    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


def safe_collect_package(
    package_name: str,
) -> None:
    """
    Collect an optional package without failing the entire build.
    """

    try:
        collect_package(
            package_name
        )

    except Exception as exc:
        print(
            f"[PyInstaller] "
            f"Skipping optional package "
            f"{package_name}: {exc}"
        )


def safe_collect_submodules(
    package_name: str,
) -> None:
    """
    Safely collect hidden submodules.
    """

    global hiddenimports

    try:
        hiddenimports += collect_submodules(
            package_name
        )

    except Exception as exc:
        print(
            f"[PyInstaller] "
            f"Unable to collect submodules "
            f"for {package_name}: {exc}"
        )


def deduplicate_sequence(
    values,
):
    """
    Preserve order while removing duplicates.
    """

    result = []
    seen = set()

    for value in values:

        key = repr(
            value
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            value
        )

    return result


# ============================================================
# Application Modules
# ============================================================

# The project uses routers / factories / pipelines and some
# components may be loaded indirectly.
safe_collect_submodules(
    "app"
)


# Explicit pipeline entry points.
hiddenimports += [
    "app.pipeline.pdf_pipeline",
    "app.pipeline.docx_pipeline",
    "app.pipeline.pptx_pipeline",
    "app.pipeline.xlsx_pipeline",
]


# ============================================================
# GUI
# ============================================================

# ttkbootstrap uses themes and package resources.
safe_collect_submodules(
    "ttkbootstrap"
)

safe_collect_package(
    "ttkbootstrap"
)


# Pillow is required by ttkbootstrap and image-related GUI
# functionality.
safe_collect_package(
    "PIL"
)


# ============================================================
# PDF
# ============================================================

# PyMuPDF
safe_collect_package(
    "fitz"
)


# ============================================================
# DOCX
# ============================================================

safe_collect_submodules(
    "docx"
)

safe_collect_package(
    "docx"
)


# ============================================================
# PPTX
# ============================================================

safe_collect_submodules(
    "pptx"
)

safe_collect_package(
    "pptx"
)


# ============================================================
# XLSX
# ============================================================

safe_collect_submodules(
    "openpyxl"
)

safe_collect_package(
    "openpyxl"
)


# ============================================================
# PostgreSQL
# ============================================================

safe_collect_submodules(
    "psycopg"
)

safe_collect_package(
    "psycopg"
)

# psycopg[binary] installs the optimized binary implementation.
safe_collect_package(
    "psycopg_binary"
)


# ============================================================
# YAML / Configuration
# ============================================================

safe_collect_package(
    "yaml"
)


# ============================================================
# OCR
# ============================================================
#
# Required for scanned PDF / image OCR functionality.
#
# These packages increase EXE size, but collecting them here
# avoids runtime errors caused by dynamically loaded OCR assets
# and ONNX Runtime binaries.
# ============================================================

safe_collect_package(
    "rapidocr"
)

safe_collect_package(
    "onnxruntime"
)


# ============================================================
# Windows COM / Legacy PowerPoint
# ============================================================
#
# Used when legacy Microsoft PowerPoint COM automation is
# available.
#
# PyInstaller handles most pywin32 components automatically,
# but explicit hidden imports improve OneFile reliability.
# ============================================================

hiddenimports += [
    "pythoncom",
    "pywintypes",
    "win32api",
    "win32com",
    "win32com.client",
    "win32com.client.dynamic",
    "win32com.client.gencache",
]


safe_collect_submodules(
    "win32com"
)


# ============================================================
# Application Configuration
# ============================================================

config_file = (
    project_root
    / "config"
    / "config.yaml"
)

if not config_file.exists():
    raise FileNotFoundError(
        f"Required configuration file not found: "
        f"{config_file}"
    )

datas.append(
    (
        str(
            config_file
        ),
        "config",
    )
)


# ============================================================
# Deduplicate
# ============================================================

hiddenimports = sorted(
    set(
        hiddenimports
    )
)

datas = deduplicate_sequence(
    datas
)

binaries = deduplicate_sequence(
    binaries
)


# ============================================================
# Debug Information
# ============================================================

print(
    "============================================================"
)

print(
    "[PyInstaller] Document Ingestion Platform"
)

print(
    f"[PyInstaller] Project root: {project_root}"
)

print(
    f"[PyInstaller] Entry script: {entry_script}"
)

print(
    f"[PyInstaller] Hidden imports: {len(hiddenimports)}"
)

print(
    f"[PyInstaller] Data entries: {len(datas)}"
)

print(
    f"[PyInstaller] Binary entries: {len(binaries)}"
)

print(
    "============================================================"
)


# ============================================================
# Analysis
# ============================================================

analysis = Analysis(
    [
        str(
            entry_script
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
        # ====================================================
        # AI / Embedding
        # ====================================================
        #
        # Current desktop EXE does not provide embedding,
        # vector database or local LLM functionality.
        #

        "torch",
        "transformers",
        "sentence_transformers",
        "qdrant_client",

        # ====================================================
        # Development / Notebook
        # ====================================================

        "matplotlib",
        "notebook",
        "jupyter",
        "IPython",

        # ====================================================
        # Legacy PostgreSQL Driver
        # ====================================================

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
# OneFile Windows GUI EXE
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

    # UPX disabled:
    # more stable for Python native DLLs such as
    # psycopg / onnxruntime / PyMuPDF.
    upx=False,

    # ========================================================
    # Windows GUI
    # ========================================================

    console=False,

    # Keep PyInstaller's windowed traceback support.
    disable_windowed_traceback=False,
)