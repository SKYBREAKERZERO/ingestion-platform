from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import traceback
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    EXTENDED,
    LEFT,
    NORMAL,
    RIGHT,
    VERTICAL,
    WORD,
    X,
    Y,
)
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from typing import Any

import yaml


# ============================================================
# User PostgreSQL Configuration
# ============================================================
#
# Distribution remains a single EXE.
#
# Runtime PostgreSQL settings are stored outside the EXE:
#
# Windows:
#   %LOCALAPPDATA%\DocumentIngestionPlatform\config.yaml
#
# The password is NEVER written to this YAML file.
# It is provided through POSTGRES_PASSWORD.
#
# ConfigLoader already supports CONFIG_FILE, therefore the GUI
# can point the existing database layer to this user-writable
# configuration without changing the document pipelines.
# ============================================================


def get_user_config_directory() -> Path:

    if os.name == "nt":

        local_app_data = os.getenv(
            "LOCALAPPDATA"
        )

        if (
            local_app_data
            and local_app_data.strip()
        ):
            return (
                Path(
                    local_app_data
                )
                / "DocumentIngestionPlatform"
            )

    return (
        Path.home()
        / ".document-ingestion-platform"
    )


USER_CONFIG_DIR = (
    get_user_config_directory()
)

USER_POSTGRES_CONFIG_FILE = (
    USER_CONFIG_DIR
    / "config.yaml"
)


def activate_user_postgres_config() -> None:
    """
    Activate the GUI-managed user config when present.

    An explicitly supplied CONFIG_FILE environment variable wins.
    """

    existing_config_file = os.getenv(
        "CONFIG_FILE"
    )

    if (
        existing_config_file
        and existing_config_file.strip()
    ):
        return

    if USER_POSTGRES_CONFIG_FILE.is_file():

        os.environ[
            "CONFIG_FILE"
        ] = str(
            USER_POSTGRES_CONFIG_FILE
        )


def hydrate_postgres_password_from_windows_user_env() -> None:
    """
    Load a remembered POSTGRES_PASSWORD directly from HKCU.

    This avoids depending on whether the parent PowerShell / Explorer
    process has refreshed its environment after the password was saved.
    """

    if os.getenv(
        "POSTGRES_PASSWORD"
    ):
        return

    if os.name != "nt":
        return

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_READ,
        ) as key:

            value, _ = (
                winreg.QueryValueEx(
                    key,
                    "POSTGRES_PASSWORD",
                )
            )

        if (
            isinstance(
                value,
                str,
            )
            and value
        ):
            os.environ[
                "POSTGRES_PASSWORD"
            ] = value

    except (
        FileNotFoundError,
        OSError,
    ):
        pass


activate_user_postgres_config()
hydrate_postgres_password_from_windows_user_env()


from app.pipeline.pipeline_factory import PipelineFactory
from app.model.chapter import Chapter
from app.model.content import Content
from app.model.document import Document
from app.model.section import Section
from app.storage.postgres_storage import PostgresStorage



# ============================================================
# Application Constants
# ============================================================

APP_NAME = "Document Ingestion Platform"
APP_VERSION = "1.0.0"

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
}

JSON_FILE_TYPES = [
    (
        "Document Ingestion JSON",
        "*.json",
    ),
    (
        "All Files",
        "*.*",
    ),
]


SUPPORTED_FILE_TYPES = [
    (
        "Supported Documents",
        "*.pdf *.docx *.pptx *.xlsx",
    ),
    (
        "PDF Documents",
        "*.pdf",
    ),
    (
        "Word Documents",
        "*.docx",
    ),
    (
        "PowerPoint Documents",
        "*.pptx",
    ),
    (
        "Excel Documents",
        "*.xlsx",
    ),
    (
        "All Files",
        "*.*",
    ),
]


# ============================================================
# Runtime Path
# ============================================================


def get_base_directory() -> Path:
    """
    Python:
        Project root

    PyInstaller:
        EXE directory
    """

    if getattr(
        sys,
        "frozen",
        False,
    ):
        return Path(
            sys.executable
        ).resolve().parent

    return Path(
        __file__
    ).resolve().parents[2]


BASE_DIR = get_base_directory()

LOG_DIR = (
    BASE_DIR
    / "logs"
)

DEFAULT_OUTPUT_DIR = (
    BASE_DIR
    / "output"
)


# ============================================================
# Logging
# ============================================================


def configure_gui_logging() -> logging.Logger:
    """
    GUI 独立日志。

    文件：
        logs/gui.log

    支持日志轮转：
        5 MB × 5
    """

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger(
        "document_ingestion.gui"
    )

    logger.setLevel(
        logging.INFO
    )

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        (
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )

    file_handler = RotatingFileHandler(
        filename=(
            LOG_DIR
            / "gui.log"
        ),
        maxBytes=(
            5
            * 1024
            * 1024
        ),
        backupCount=5,
        encoding="utf-8",
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        file_handler
    )

    return logger


LOGGER = configure_gui_logging()


# ============================================================
# Data Models
# ============================================================


@dataclass(frozen=True)
class PostgreSQLSettings:
    host: str
    port: int
    database: str
    user: str
    connect_timeout: int


@dataclass(frozen=True)
class ProcessingOptions:
    output_directory: Path
    save_json: bool
    save_database: bool


@dataclass(frozen=True)
class FileFailure:
    file_path: Path
    error_type: str
    error_message: str


@dataclass(frozen=True)
class BatchSummary:
    success: int
    failed: int
    total: int
    cancelled: bool = False


# ============================================================
# GUI
# ============================================================


class DocumentIngestionGUI:
    """
    Desktop GUI for Document Ingestion Platform.

    GUI 层只负责：

        - 文件选择
        - 参数输入
        - 用户交互
        - 进度显示
        - 日志显示
        - 后台任务调度

    实际文档解析仍交给：

        PipelineFactory
    """

    def __init__(
        self,
        root: tk.Tk,
    ) -> None:

        self.root = root

        self.selected_files: list[
            Path
        ] = []

        self.selected_json_files: list[
            Path
        ] = []

        self.json_import_failures: list[
            FileFailure
        ] = []

        self.json_import_thread: (
            threading.Thread
            | None
        ) = None

        self.failures: list[
            FileFailure
        ] = []

        self.event_queue: queue.Queue[
            tuple[str, Any]
        ] = queue.Queue()

        self.processing_thread: (
            threading.Thread
            | None
        ) = None

        self.postgres_test_thread: (
            threading.Thread
            | None
        ) = None

        self.postgres_schema_thread: (
            threading.Thread
            | None
        ) = None

        self.postgres_connection_verified = False

        self.is_processing = False

        self.cancel_requested = (
            threading.Event()
        )

        self._configure_window()

        self._configure_styles()

        self._create_variables()

        self._build_ui()

        self._bind_postgres_setting_traces()

        self._poll_events()

        LOGGER.info(
            "GUI application started | "
            "version=%s | "
            "base_dir=%s",
            APP_VERSION,
            BASE_DIR,
        )

    # ========================================================
    # Window
    # ========================================================

    def _configure_window(
        self,
    ) -> None:

        self.root.title(
            (
                f"{APP_NAME} "
                f"v{APP_VERSION}"
            )
        )

        self.root.geometry(
            "1480x900"
        )

        self.root.minsize(
            1180,
            760,
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
        )

    def _configure_styles(
        self,
    ) -> None:
        """
        Configure a modern light desktop appearance.

        Business logic is intentionally untouched in this step.
        """

        style = ttk.Style()

        style.configure(
            "AppHeader.TLabel",
            font=(
                "Segoe UI",
                22,
                "bold",
            ),
        )

        style.configure(
            "AppSubtitle.TLabel",
            font=(
                "Segoe UI",
                10,
            ),
        )

        style.configure(
            "Card.TLabelframe.Label",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        )

        style.configure(
            "Small.TLabel",
            font=(
                "Segoe UI",
                9,
            ),
        )

        style.configure(
            "StatusBold.TLabel",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        )

    # ========================================================
    # Variables
    # ========================================================

    def _create_variables(
        self,
    ) -> None:

        self.output_directory_var = (
            tk.StringVar(
                value=str(
                    DEFAULT_OUTPUT_DIR
                )
            )
        )

        self.save_json_var = (
            tk.BooleanVar(
                value=True
            )
        )

        self.save_database_var = (
            tk.BooleanVar(
                value=False
            )
        )

        self.status_var = (
            tk.StringVar(
                value="Ready"
            )
        )

        self.current_file_var = (
            tk.StringVar(
                value="No file selected."
            )
        )

        self.progress_var = (
            tk.DoubleVar(
                value=0
            )
        )

        self.progress_text_var = (
            tk.StringVar(
                value="0%"
            )
        )

        self.summary_var = (
            tk.StringVar(
                value=(
                    "Success: 0    "
                    "Failed: 0    "
                    "Total: 0"
                )
            )
        )

        self.file_count_var = (
            tk.StringVar(
                value=(
                    "0 files selected"
                )
            )
        )

        self.json_file_count_var = (
            tk.StringVar(
                value=(
                    "0 JSON files selected"
                )
            )
        )

        self.json_import_status_var = (
            tk.StringVar(
                value="Ready"
            )
        )

        self.json_import_current_file_var = (
            tk.StringVar(
                value=(
                    "Select one or more JSON files."
                )
            )
        )

        self.json_import_progress_var = (
            tk.DoubleVar(
                value=0
            )
        )

        self.json_import_progress_text_var = (
            tk.StringVar(
                value="0%"
            )
        )

        self.json_import_summary_var = (
            tk.StringVar(
                value=(
                    "Success: 0    "
                    "Failed: 0    "
                    "Total: 0"
                )
            )
        )

        postgres_profile = (
            self._read_postgres_profile()
        )

        self.postgres_host_var = (
            tk.StringVar(
                value=postgres_profile[
                    "host"
                ]
            )
        )

        self.postgres_port_var = (
            tk.StringVar(
                value=str(
                    postgres_profile[
                        "port"
                    ]
                )
            )
        )

        self.postgres_database_var = (
            tk.StringVar(
                value=postgres_profile[
                    "database"
                ]
            )
        )

        self.postgres_user_var = (
            tk.StringVar(
                value=postgres_profile[
                    "user"
                ]
            )
        )

        self.postgres_timeout_var = (
            tk.StringVar(
                value=str(
                    postgres_profile[
                        "connect_timeout"
                    ]
                )
            )
        )

        # Password fields are intentionally never populated from disk.
        self.postgres_password_var = (
            tk.StringVar(
                value=""
            )
        )

        self.postgres_remember_password_var = (
            tk.BooleanVar(
                value=False
            )
        )

        self.postgres_connection_status_var = (
            tk.StringVar(
                value=(
                    "Not tested"
                )
            )
        )

        self.postgres_schema_status_var = (
            tk.StringVar(
                value=(
                    "Required tables not verified"
                )
            )
        )

        self.postgres_password_status_var = (
            tk.StringVar(
                value=(
                    "Password available for this session"
                    if os.getenv(
                        "POSTGRES_PASSWORD"
                    )
                    else (
                        "Password is not configured"
                    )
                )
            )
        )

        self.postgres_config_path_var = (
            tk.StringVar(
                value=str(
                    USER_POSTGRES_CONFIG_FILE
                )
            )
        )

    # ========================================================
    # Main UI
    # ========================================================

    def _build_ui(
        self,
    ) -> None:

        shell = ttk.Frame(
            self.root,
            padding=(
                24,
                20,
                24,
                16,
            ),
        )

        shell.pack(
            fill=BOTH,
            expand=True,
        )

        self._build_header(
            shell
        )

        ttk.Separator(
            shell,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        # ====================================================
        # Top-level work pages
        # ====================================================
        #
        # Page 1:
        #   Original document conversion
        #
        # Page 2:
        #   Existing JSON -> PostgreSQL
        #
        self.main_notebook = ttk.Notebook(
            shell,
            bootstyle="primary",
        )

        self.main_notebook.pack(
            fill=BOTH,
            expand=True,
        )

        document_tab = ttk.Frame(
            self.main_notebook,
            padding=(
                4,
                14,
                4,
                4,
            ),
        )

        json_import_tab = ttk.Frame(
            self.main_notebook,
            padding=(
                4,
                14,
                4,
                4,
            ),
        )

        postgres_settings_tab = ttk.Frame(
            self.main_notebook,
            padding=(
                4,
                14,
                4,
                4,
            ),
        )

        self.main_notebook.add(
            document_tab,
            text="  Document Conversion  ",
        )

        self.main_notebook.add(
            json_import_tab,
            text="  JSON → PostgreSQL  ",
        )

        self.main_notebook.add(
            postgres_settings_tab,
            text="  PostgreSQL Settings  ",
        )

        self._build_document_conversion_page(
            document_tab
        )

        self._build_json_import_page(
            json_import_tab
        )

        self._build_postgres_settings_page(
            postgres_settings_tab
        )

        self._build_status_bar(
            shell
        )

    def _build_document_conversion_page(
        self,
        parent: ttk.Frame,
    ) -> None:
        """
        Build the existing document conversion workspace.

        Business flow:
            PDF / DOCX / PPTX / XLSX
                -> Pipeline
                -> JSON / PostgreSQL
        """

        workspace = ttk.Frame(
            parent
        )

        workspace.pack(
            fill=BOTH,
            expand=True,
        )

        workspace.columnconfigure(
            0,
            weight=5,
            uniform="main-columns",
        )

        workspace.columnconfigure(
            1,
            weight=4,
            uniform="main-columns",
        )

        workspace.columnconfigure(
            2,
            weight=5,
            uniform="main-columns",
        )

        workspace.rowconfigure(
            0,
            weight=1,
        )

        left_panel = ttk.Frame(
            workspace
        )

        left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(
                0,
                8,
            ),
        )

        center_panel = ttk.Frame(
            workspace
        )

        center_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=8,
        )

        right_panel = ttk.Frame(
            workspace
        )

        right_panel.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(
                8,
                0,
            ),
        )

        self._build_input_section(
            left_panel
        )

        self._build_output_section(
            center_panel
        )

        self._build_options_section(
            center_panel
        )

        self._build_action_section(
            center_panel
        )

        self._build_progress_section(
            right_panel
        )

        self._build_log_section(
            right_panel
        )

    # ========================================================
    # Header
    # ========================================================

    def _build_header(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.Frame(
            parent
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                14,
            ),
        )

        title_area = ttk.Frame(
            frame
        )

        title_area.pack(
            side=LEFT,
            fill=X,
            expand=True,
        )

        ttk.Label(
            title_area,
            text=APP_NAME,
            style="AppHeader.TLabel",
            bootstyle="dark",
        ).pack(
            anchor="w"
        )

        ttk.Label(
            title_area,
            text=(
                "Document conversion · Structured JSON · "
                "PostgreSQL storage"
            ),
            style="AppSubtitle.TLabel",
            bootstyle="secondary",
        ).pack(
            anchor="w",
            pady=(
                4,
                0,
            ),
        )

        info_area = ttk.Frame(
            frame
        )

        info_area.pack(
            side=RIGHT,
            anchor="ne",
        )

        ttk.Label(
            info_area,
            text=(
                "PDF   DOCX   PPTX   XLSX"
            ),
            bootstyle="secondary",
        ).pack(
            anchor="e"
        )

        ttk.Label(
            info_area,
            text=(
                f"v{APP_VERSION}"
            ),
            bootstyle="primary",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="e",
            pady=(
                5,
                0,
            ),
        )

    # ========================================================
    # Input Files
    # ========================================================

    def _build_input_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="1. Input Files",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        toolbar = ttk.Frame(
            frame
        )

        toolbar.pack(
            fill=X,
            pady=(
                0,
                10,
            ),
        )

        self.add_files_button = (
            ttk.Button(
                toolbar,
                text="＋  Add Files",
                command=(
                    self.select_files
                ),
                bootstyle="primary",
            )
        )

        self.add_files_button.pack(
            side=LEFT
        )

        self.remove_files_button = (
            ttk.Button(
                toolbar,
                text="Remove",
                command=(
                    self.remove_selected_files
                ),
                bootstyle="secondary-outline",
            )
        )

        self.remove_files_button.pack(
            side=LEFT,
            padx=(
                8,
                0,
            ),
        )

        self.clear_files_button = (
            ttk.Button(
                toolbar,
                text="Clear",
                command=(
                    self.clear_files
                ),
                bootstyle="secondary-outline",
            )
        )

        self.clear_files_button.pack(
            side=LEFT,
            padx=(
                8,
                0,
            ),
        )

        list_container = ttk.Frame(
            frame
        )

        list_container.pack(
            fill=BOTH,
            expand=True,
        )

        self.file_listbox = (
            tk.Listbox(
                list_container,
                height=24,
                selectmode=EXTENDED,
                activestyle="none",
                font=(
                    "Segoe UI",
                    10,
                ),
                borderwidth=1,
                relief="solid",
                highlightthickness=0,
                selectborderwidth=0,
            )
        )

        scrollbar = ttk.Scrollbar(
            list_container,
            orient=VERTICAL,
            command=(
                self.file_listbox
                .yview
            ),
            bootstyle="round",
        )

        self.file_listbox.configure(
            yscrollcommand=(
                scrollbar.set
            )
        )

        self.file_listbox.pack(
            side=LEFT,
            fill=BOTH,
            expand=True,
        )

        scrollbar.pack(
            side=RIGHT,
            fill=Y,
        )

        footer = ttk.Frame(
            frame
        )

        footer.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        ttk.Label(
            footer,
            text=(
                "Supported: PDF / DOCX / PPTX / XLSX"
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            side=LEFT
        )

        ttk.Label(
            footer,
            textvariable=(
                self.file_count_var
            ),
            bootstyle="primary",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            side=RIGHT
        )

    # ========================================================
    # Output
    # ========================================================

    def _build_output_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="2. Output",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        ttk.Label(
            frame,
            text="Output Directory",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            pady=(
                0,
                6,
            ),
        )

        row = ttk.Frame(
            frame
        )

        row.pack(
            fill=X
        )

        self.output_entry = (
            ttk.Entry(
                row,
                textvariable=(
                    self.output_directory_var
                ),
                bootstyle="primary",
            )
        )

        self.output_entry.pack(
            side=LEFT,
            fill=X,
            expand=True,
            padx=(
                0,
                8,
            ),
        )

        self.output_button = (
            ttk.Button(
                row,
                text="Browse",
                command=(
                    self.select_output_directory
                ),
                bootstyle="secondary-outline",
            )
        )

        self.output_button.pack(
            side=RIGHT
        )

    # ========================================================
    # Processing Options
    # ========================================================

    def _build_options_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="3. Processing Options",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        ttk.Label(
            frame,
            text="Output Targets",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            pady=(
                0,
                9,
            ),
        )

        self.json_checkbox = (
            ttk.Checkbutton(
                frame,
                text="Generate JSON",
                variable=(
                    self.save_json_var
                ),
                bootstyle="primary-round-toggle",
            )
        )

        self.json_checkbox.pack(
            anchor="w",
            pady=(
                0,
                10,
            ),
        )

        self.database_checkbox = (
            ttk.Checkbutton(
                frame,
                text="Save to PostgreSQL",
                variable=(
                    self.save_database_var
                ),
                bootstyle="primary-round-toggle",
            )
        )

        self.database_checkbox.pack(
            anchor="w"
        )

        ttk.Separator(
            frame,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                14,
                10,
            ),
        )

        ttk.Label(
            frame,
            text=(
                "PostgreSQL password is requested only "
                "when database output is enabled."
            ),
            bootstyle="secondary",
            wraplength=330,
            justify=LEFT,
            style="Small.TLabel",
        ).pack(
            anchor="w"
        )

    # ========================================================
    # Actions
    # ========================================================

    def _build_action_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="4. Actions",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
        )

        self.convert_button = (
            ttk.Button(
                frame,
                text="▶  Convert",
                command=(
                    self.start_processing
                ),
                bootstyle="primary",
            )
        )

        self.convert_button.pack(
            fill=X,
            ipady=5,
        )

        self.cancel_button = (
            ttk.Button(
                frame,
                text="Cancel",
                command=(
                    self.cancel_processing
                ),
                state=DISABLED,
                bootstyle="danger-outline",
            )
        )

        self.cancel_button.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        ttk.Label(
            frame,
            text=(
                "Cancel stops after the current "
                "document finishes."
            ),
            bootstyle="secondary",
            wraplength=330,
            justify=LEFT,
            style="Small.TLabel",
        ).pack(
            anchor="w",
            pady=(
                12,
                0,
            ),
        )

    # ========================================================
    # Progress
    # ========================================================

    def _build_progress_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="5. Processing Status",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        header = ttk.Frame(
            frame
        )

        header.pack(
            fill=X
        )

        ttk.Label(
            header,
            textvariable=(
                self.status_var
            ),
            style="StatusBold.TLabel",
            bootstyle="dark",
        ).pack(
            side=LEFT
        )

        ttk.Label(
            header,
            textvariable=(
                self.progress_text_var
            ),
            bootstyle="primary",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side=RIGHT
        )

        self.progress_bar = (
            ttk.Progressbar(
                frame,
                variable=(
                    self.progress_var
                ),
                maximum=100,
                bootstyle="primary-striped",
            )
        )

        self.progress_bar.pack(
            fill=X,
            pady=(
                12,
                10,
            ),
        )

        ttk.Label(
            frame,
            textvariable=(
                self.current_file_var
            ),
            wraplength=400,
            justify=LEFT,
            bootstyle="secondary",
        ).pack(
            anchor="w",
            pady=(
                0,
                8,
            ),
        )

        ttk.Separator(
            frame,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                2,
                8,
            ),
        )

        ttk.Label(
            frame,
            textvariable=(
                self.summary_var
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w"
        )

    # ========================================================
    # Log
    # ========================================================

    def _build_log_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="Execution Log",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        text_container = ttk.Frame(
            frame
        )

        text_container.pack(
            fill=BOTH,
            expand=True,
        )

        self.log_text = tk.Text(
            text_container,
            state=DISABLED,
            wrap=WORD,
            height=20,
            font=(
                "Cascadia Mono",
                9,
            ),
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            padx=10,
            pady=10,
        )

        scrollbar = ttk.Scrollbar(
            text_container,
            orient=VERTICAL,
            command=(
                self.log_text
                .yview
            ),
            bootstyle="round",
        )

        self.log_text.configure(
            yscrollcommand=(
                scrollbar.set
            )
        )

        self.log_text.pack(
            side=LEFT,
            fill=BOTH,
            expand=True,
        )

        scrollbar.pack(
            side=RIGHT,
            fill=Y,
        )

    # ========================================================
    # Status Bar
    # ========================================================

    def _build_status_bar(
        self,
        parent: ttk.Frame,
    ) -> None:

        ttk.Separator(
            parent,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                14,
                8,
            ),
        )

        frame = ttk.Frame(
            parent
        )

        frame.pack(
            fill=X
        )

        ttk.Label(
            frame,
            text="Ready",
            bootstyle="success",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            side=LEFT
        )

        ttk.Label(
            frame,
            text=(
                "Document Ingestion Platform"
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            side=LEFT,
            padx=(
                12,
                0,
            ),
        )

        ttk.Label(
            frame,
            text=(
                f"Version {APP_VERSION}"
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            side=RIGHT
        )

    # ========================================================
    # Input Files
    # ========================================================

    # ========================================================
    # PostgreSQL Settings Page
    # ========================================================

    def _build_postgres_settings_page(
        self,
        parent: ttk.Frame,
    ) -> None:
        """
        PostgreSQL connection configuration page.

        The page configures:
            - Host
            - Port
            - Database
            - User
            - Password
            - Connect timeout

        Non-secret settings:
            %LOCALAPPDATA%/DocumentIngestionPlatform/config.yaml

        Password:
            POSTGRES_PASSWORD
            optionally persisted in the current Windows user's
            environment by the existing credential mechanism.
        """

        workspace = ttk.Frame(
            parent
        )

        workspace.pack(
            fill=BOTH,
            expand=True,
        )

        workspace.columnconfigure(
            0,
            weight=3,
        )

        workspace.columnconfigure(
            1,
            weight=2,
        )

        workspace.rowconfigure(
            0,
            weight=1,
        )

        left_panel = ttk.Frame(
            workspace
        )

        left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(
                0,
                10,
            ),
        )

        right_panel = ttk.Frame(
            workspace
        )

        right_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(
                10,
                0,
            ),
        )

        self._build_postgres_connection_card(
            left_panel
        )

        self._build_postgres_actions_card(
            left_panel
        )

        self._build_postgres_status_card(
            right_panel
        )

        self._build_postgres_help_card(
            right_panel
        )

    def _build_postgres_connection_card(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="1. Connection",
            padding=18,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        frame.columnconfigure(
            1,
            weight=1,
        )

        fields = (
            (
                "Host",
                self.postgres_host_var,
            ),
            (
                "Port",
                self.postgres_port_var,
            ),
            (
                "Database",
                self.postgres_database_var,
            ),
            (
                "User",
                self.postgres_user_var,
            ),
            (
                "Connect Timeout (sec)",
                self.postgres_timeout_var,
            ),
        )

        self.postgres_setting_entries: list[
            ttk.Entry
        ] = []

        for row_index, (
            label_text,
            variable,
        ) in enumerate(
            fields
        ):

            ttk.Label(
                frame,
                text=label_text,
                font=(
                    "Segoe UI",
                    9,
                    "bold",
                ),
            ).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(
                    0,
                    14,
                ),
                pady=7,
            )

            entry = ttk.Entry(
                frame,
                textvariable=variable,
                bootstyle="primary",
            )

            entry.grid(
                row=row_index,
                column=1,
                sticky="ew",
                pady=7,
            )

            self.postgres_setting_entries.append(
                entry
            )

        password_row = len(
            fields
        )

        ttk.Label(
            frame,
            text="Password",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).grid(
            row=password_row,
            column=0,
            sticky="w",
            padx=(
                0,
                14,
            ),
            pady=7,
        )

        self.postgres_password_entry = (
            ttk.Entry(
                frame,
                textvariable=(
                    self.postgres_password_var
                ),
                show="●",
                bootstyle="primary",
            )
        )

        self.postgres_password_entry.grid(
            row=password_row,
            column=1,
            sticky="ew",
            pady=7,
        )

        self.postgres_setting_entries.append(
            self.postgres_password_entry
        )

        self.postgres_remember_checkbox = (
            ttk.Checkbutton(
                frame,
                text=(
                    "Remember password on this computer "
                    "(Windows user environment)"
                ),
                variable=(
                    self.postgres_remember_password_var
                ),
                bootstyle="success-round-toggle",
            )
        )

        self.postgres_remember_checkbox.grid(
            row=(
                password_row
                + 1
            ),
            column=1,
            sticky="w",
            pady=(
                10,
                4,
            ),
        )

        ttk.Label(
            frame,
            text=(
                "The password is never written to config.yaml "
                "or application logs."
            ),
            wraplength=560,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).grid(
            row=(
                password_row
                + 2
            ),
            column=1,
            sticky="w",
            pady=(
                3,
                0,
            ),
        )

    def _build_postgres_actions_card(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="2. Actions",
            padding=18,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
        )

        button_row = ttk.Frame(
            frame
        )

        button_row.pack(
            fill=X
        )

        self.postgres_test_button = (
            ttk.Button(
                button_row,
                text="✓  Test Connection",
                command=(
                    self.start_postgres_connection_test
                ),
                bootstyle="primary",
            )
        )

        self.postgres_test_button.pack(
            side=LEFT,
            fill=X,
            expand=True,
        )

        self.postgres_save_button = (
            ttk.Button(
                button_row,
                text="Save Settings",
                command=(
                    self.save_postgres_settings
                ),
                bootstyle="success",
            )
        )

        self.postgres_save_button.pack(
            side=LEFT,
            fill=X,
            expand=True,
            padx=(
                10,
                0,
            ),
        )

        secondary_row = ttk.Frame(
            frame
        )

        secondary_row.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        self.postgres_defaults_button = (
            ttk.Button(
                secondary_row,
                text="Restore Defaults",
                command=(
                    self.restore_postgres_defaults
                ),
                bootstyle="secondary-outline",
            )
        )

        self.postgres_defaults_button.pack(
            side=LEFT,
            fill=X,
            expand=True,
        )

        self.postgres_clear_password_button = (
            ttk.Button(
                secondary_row,
                text="Clear Saved Password",
                command=(
                    self.clear_saved_postgres_password
                ),
                bootstyle="danger-outline",
            )
        )

        self.postgres_clear_password_button.pack(
            side=LEFT,
            fill=X,
            expand=True,
            padx=(
                10,
                0,
            ),
        )

        schema_row = ttk.Frame(
            frame
        )

        schema_row.pack(
            fill=X,
            pady=(
                12,
                0,
            ),
        )

        self.postgres_create_tables_button = (
            ttk.Button(
                schema_row,
                text="▦  Create / Verify Required Tables",
                command=(
                    self.start_postgres_schema_initialization
                ),
                state=DISABLED,
                bootstyle="info",
            )
        )

        self.postgres_create_tables_button.pack(
            fill=X,
            ipady=4,
        )

        ttk.Label(
            schema_row,
            text=(
                "Enabled only after a successful connection test. "
                "Existing tables and data are not deleted."
            ),
            wraplength=560,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w",
            pady=(
                8,
                0,
            ),
        )

    def _build_postgres_status_card(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="Status",
            padding=18,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        ttk.Label(
            frame,
            text="Connection",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        self.postgres_connection_status_label = (
            ttk.Label(
                frame,
                textvariable=(
                    self.postgres_connection_status_var
                ),
                bootstyle="secondary",
                font=(
                    "Segoe UI",
                    11,
                    "bold",
                ),
            )
        )

        self.postgres_connection_status_label.pack(
            anchor="w",
            pady=(
                4,
                14,
            ),
        )

        ttk.Label(
            frame,
            text="Credential",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        self.postgres_password_status_label = (
            ttk.Label(
                frame,
                textvariable=(
                    self.postgres_password_status_var
                ),
                bootstyle=(
                    "success"
                    if os.getenv(
                        "POSTGRES_PASSWORD"
                    )
                    else "warning"
                ),
            )
        )

        self.postgres_password_status_label.pack(
            anchor="w",
            pady=(
                4,
                14,
            ),
        )

        ttk.Label(
            frame,
            text="Database Schema",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        self.postgres_schema_status_label = (
            ttk.Label(
                frame,
                textvariable=(
                    self.postgres_schema_status_var
                ),
                bootstyle="secondary",
                wraplength=430,
                justify=LEFT,
            )
        )

        self.postgres_schema_status_label.pack(
            anchor="w",
            pady=(
                4,
                14,
            ),
        )

        ttk.Label(
            frame,
            text="User config file",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        ttk.Label(
            frame,
            textvariable=(
                self.postgres_config_path_var
            ),
            wraplength=430,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w",
            pady=(
                4,
                0,
            ),
        )

    def _build_postgres_help_card(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="New Computer Setup",
            padding=18,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        instructions = (
            "1. Install / prepare PostgreSQL or enter a remote DB host.",
            "2. Enter Host, Port, Database and User.",
            "3. Enter the PostgreSQL password.",
            "4. Click Test Connection.",
            "5. Click Create / Verify Required Tables.",
            "6. Click Save Settings.",
            "7. Use Document Conversion or JSON → PostgreSQL.",
        )

        for instruction in instructions:

            ttk.Label(
                frame,
                text=instruction,
                wraplength=430,
                justify=LEFT,
                bootstyle="secondary",
            ).pack(
                anchor="w",
                pady=(
                    0,
                    10,
                ),
            )

        ttk.Separator(
            frame,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                4,
                12,
            ),
        )

        ttk.Label(
            frame,
            text=(
                "The distributed application can still be a single EXE. "
                "This page creates only a per-user runtime configuration "
                "under LocalAppData."
            ),
            wraplength=430,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w"
        )

    # ========================================================
    # PostgreSQL Settings - Load / Validate / Save
    # ========================================================

    @staticmethod
    def _default_postgres_profile() -> dict[
        str,
        Any,
    ]:

        return {
            "host": "127.0.0.1",
            "port": 5432,
            "database": "rag",
            "user": "postgres",
            "connect_timeout": 10,
        }

    @classmethod
    def _read_postgres_profile(
        cls,
    ) -> dict[str, Any]:

        profile = dict(
            cls._default_postgres_profile()
        )

        candidate_paths: list[Path] = []

        environment_path = os.getenv(
            "CONFIG_FILE"
        )

        if (
            environment_path
            and environment_path.strip()
        ):
            candidate_paths.append(
                Path(
                    environment_path
                ).expanduser()
            )

        if USER_POSTGRES_CONFIG_FILE not in candidate_paths:
            candidate_paths.append(
                USER_POSTGRES_CONFIG_FILE
            )

        # Development fallback only.
        candidate_paths.append(
            (
                Path(
                    __file__
                ).resolve().parents[2]
                / "config"
                / "config.yaml"
            )
        )

        for path in candidate_paths:

            try:
                if not path.is_file():
                    continue

                with path.open(
                    "r",
                    encoding="utf-8",
                ) as file:

                    raw = yaml.safe_load(
                        file
                    )

                if not isinstance(
                    raw,
                    dict,
                ):
                    continue

                database = raw.get(
                    "database"
                )

                if not isinstance(
                    database,
                    dict,
                ):
                    continue

                host = database.get(
                    "host"
                )

                port = database.get(
                    "port"
                )

                database_name = (
                    database.get(
                        "database"
                    )
                )

                user = database.get(
                    "user"
                )

                timeout = database.get(
                    "connect_timeout"
                )

                if (
                    isinstance(
                        host,
                        str,
                    )
                    and host.strip()
                ):
                    profile[
                        "host"
                    ] = host.strip()

                try:
                    parsed_port = int(
                        port
                    )

                    if (
                        1
                        <= parsed_port
                        <= 65535
                    ):
                        profile[
                            "port"
                        ] = parsed_port

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

                if (
                    isinstance(
                        database_name,
                        str,
                    )
                    and database_name.strip()
                ):
                    profile[
                        "database"
                    ] = (
                        database_name.strip()
                    )

                if (
                    isinstance(
                        user,
                        str,
                    )
                    and user.strip()
                ):
                    profile[
                        "user"
                    ] = user.strip()

                try:
                    parsed_timeout = int(
                        timeout
                    )

                    if parsed_timeout > 0:
                        profile[
                            "connect_timeout"
                        ] = parsed_timeout

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

                break

            except (
                OSError,
                yaml.YAMLError,
            ):
                continue

        return profile

    def _collect_postgres_settings(
        self,
    ) -> PostgreSQLSettings | None:

        host = (
            self.postgres_host_var
            .get()
            .strip()
        )

        database = (
            self.postgres_database_var
            .get()
            .strip()
        )

        user = (
            self.postgres_user_var
            .get()
            .strip()
        )

        if not host:
            messagebox.showwarning(
                "PostgreSQL Settings",
                "Host cannot be empty.",
                parent=self.root,
            )

            return None

        if not database:
            messagebox.showwarning(
                "PostgreSQL Settings",
                "Database cannot be empty.",
                parent=self.root,
            )

            return None

        if not user:
            messagebox.showwarning(
                "PostgreSQL Settings",
                "User cannot be empty.",
                parent=self.root,
            )

            return None

        try:
            port = int(
                self.postgres_port_var
                .get()
                .strip()
            )

        except ValueError:

            messagebox.showwarning(
                "PostgreSQL Settings",
                "Port must be an integer.",
                parent=self.root,
            )

            return None

        if not (
            1
            <= port
            <= 65535
        ):
            messagebox.showwarning(
                "PostgreSQL Settings",
                (
                    "Port must be between "
                    "1 and 65535."
                ),
                parent=self.root,
            )

            return None

        try:
            timeout = int(
                self.postgres_timeout_var
                .get()
                .strip()
            )

        except ValueError:

            messagebox.showwarning(
                "PostgreSQL Settings",
                (
                    "Connect timeout must "
                    "be an integer."
                ),
                parent=self.root,
            )

            return None

        if timeout <= 0:

            messagebox.showwarning(
                "PostgreSQL Settings",
                (
                    "Connect timeout must "
                    "be greater than 0."
                ),
                parent=self.root,
            )

            return None

        return PostgreSQLSettings(
            host=host,
            port=port,
            database=database,
            user=user,
            connect_timeout=timeout,
        )

    def save_postgres_settings(
        self,
    ) -> None:

        if self.is_processing:
            return

        settings = (
            self._collect_postgres_settings()
        )

        if settings is None:
            return

        password = (
            self.postgres_password_var
            .get()
        )

        remember = bool(
            self.postgres_remember_password_var
            .get()
        )

        if (
            remember
            and not password
            and not os.getenv(
                "POSTGRES_PASSWORD"
            )
        ):
            messagebox.showwarning(
                "PostgreSQL Settings",
                (
                    "Enter a password before enabling "
                    "'Remember password on this computer'."
                ),
                parent=self.root,
            )

            self.postgres_password_entry.focus_set()

            return

        # Password is applied to the current process only when the user
        # actually typed one. An existing session password is preserved.
        if password:

            os.environ[
                "POSTGRES_PASSWORD"
            ] = password

            if remember:

                try:
                    self._persist_postgres_password(
                        password
                    )

                except OSError as exc:

                    messagebox.showwarning(
                        "PostgreSQL Settings",
                        (
                            "The settings will be saved and the password "
                            "will work for this session, but Windows could "
                            "not remember the password.\n\n"
                            f"Reason: {exc}"
                        ),
                        parent=self.root,
                    )

        user_config = {
            "database": {
                "enabled": True,
                "host": settings.host,
                "port": settings.port,
                "database": settings.database,
                "user": settings.user,
                "password_env": (
                    "POSTGRES_PASSWORD"
                ),
                "connect_timeout": (
                    settings.connect_timeout
                ),
            }
        }

        try:

            USER_CONFIG_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_path = (
                USER_POSTGRES_CONFIG_FILE
                .with_suffix(
                    ".yaml.tmp"
                )
            )

            with temporary_path.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as file:

                yaml.safe_dump(
                    user_config,
                    file,
                    allow_unicode=True,
                    sort_keys=False,
                )

            temporary_path.replace(
                USER_POSTGRES_CONFIG_FILE
            )

        except OSError as exc:

            messagebox.showerror(
                "PostgreSQL Settings",
                (
                    "Unable to save PostgreSQL settings.\n\n"
                    f"{exc}"
                ),
                parent=self.root,
            )

            return

        # Make the newly saved config active immediately for all later
        # PipelineFactory / PostgresStorage objects in this process.
        os.environ[
            "CONFIG_FILE"
        ] = str(
            USER_POSTGRES_CONFIG_FILE
        )

        self.postgres_config_path_var.set(
            str(
                USER_POSTGRES_CONFIG_FILE
            )
        )

        self._refresh_postgres_password_status()

        self.postgres_connection_status_var.set(
            (
                "Settings saved. "
                "Connection test recommended."
            )
        )

        self.postgres_connection_status_label.configure(
            bootstyle="primary"
        )

        LOGGER.info(
            (
                "PostgreSQL settings saved | "
                "host=%s | port=%s | "
                "database=%s | user=%s | "
                "config=%s"
            ),
            settings.host,
            settings.port,
            settings.database,
            settings.user,
            USER_POSTGRES_CONFIG_FILE,
        )

        messagebox.showinfo(
            "PostgreSQL Settings",
            (
                "PostgreSQL settings were saved.\n\n"
                "The password was not written to config.yaml."
            ),
            parent=self.root,
        )

        # Clear plaintext from the visible field after applying it.
        self.postgres_password_var.set(
            ""
        )

    def restore_postgres_defaults(
        self,
    ) -> None:

        if self.is_processing:
            return

        self.postgres_connection_verified = False

        defaults = (
            self._default_postgres_profile()
        )

        self.postgres_host_var.set(
            defaults["host"]
        )

        self.postgres_port_var.set(
            str(
                defaults["port"]
            )
        )

        self.postgres_database_var.set(
            defaults["database"]
        )

        self.postgres_user_var.set(
            defaults["user"]
        )

        self.postgres_timeout_var.set(
            str(
                defaults[
                    "connect_timeout"
                ]
            )
        )

        self.postgres_password_var.set(
            ""
        )

        self.postgres_remember_password_var.set(
            False
        )

        self.postgres_connection_status_var.set(
            "Defaults loaded (not saved)"
        )

        self.postgres_connection_status_label.configure(
            bootstyle="secondary"
        )

    # ========================================================
    # PostgreSQL Settings - Test Connection
    # ========================================================

    def start_postgres_connection_test(
        self,
    ) -> None:

        if self.is_processing:
            return

        if (
            self.postgres_test_thread
            is not None
            and self.postgres_test_thread.is_alive()
        ):
            return

        settings = (
            self._collect_postgres_settings()
        )

        if settings is None:
            return

        typed_password = (
            self.postgres_password_var
            .get()
        )

        password = (
            typed_password
            or os.getenv(
                "POSTGRES_PASSWORD"
            )
        )

        if not password:

            messagebox.showwarning(
                "PostgreSQL Settings",
                (
                    "Enter the PostgreSQL password "
                    "before testing the connection."
                ),
                parent=self.root,
            )

            self.postgres_password_entry.focus_set()

            return

        # Make a typed password available to the current session.
        # Test Connection never persists the password by itself.
        if typed_password:

            os.environ[
                "POSTGRES_PASSWORD"
            ] = typed_password

            self._refresh_postgres_password_status()

        self.postgres_connection_status_var.set(
            "Testing connection..."
        )

        self.postgres_connection_status_label.configure(
            bootstyle="warning"
        )

        self.postgres_test_button.configure(
            state=DISABLED
        )

        self.postgres_test_thread = (
            threading.Thread(
                target=(
                    self._test_postgres_connection_worker
                ),
                kwargs={
                    "settings": settings,
                    "password": password,
                },
                daemon=True,
                name=(
                    "postgres-connection-test"
                ),
            )
        )

        self.postgres_test_thread.start()

    def _test_postgres_connection_worker(
        self,
        *,
        settings: PostgreSQLSettings,
        password: str,
    ) -> None:

        try:
            import psycopg

            with psycopg.connect(
                host=settings.host,
                port=settings.port,
                dbname=settings.database,
                user=settings.user,
                password=password,
                connect_timeout=(
                    settings.connect_timeout
                ),
            ) as connection:

                with connection.cursor() as cursor:

                    cursor.execute(
                        (
                            "SELECT "
                            "current_database(), "
                            "current_user"
                        )
                    )

                    row = cursor.fetchone()

            database_name = (
                row[0]
                if row
                else settings.database
            )

            user_name = (
                row[1]
                if row
                else settings.user
            )

            self._emit(
                "postgres_test_result",
                {
                    "success": True,
                    "message": (
                        "Connected successfully"
                    ),
                    "detail": (
                        f"Database: {database_name} | "
                        f"User: {user_name}"
                    ),
                },
            )

        except Exception as exc:

            self._emit(
                "postgres_test_result",
                {
                    "success": False,
                    "message": (
                        "Connection failed"
                    ),
                    "detail": str(
                        exc
                    ),
                },
            )

    def _handle_postgres_test_result(
        self,
        payload: Any,
    ) -> None:

        self.postgres_test_button.configure(
            state=(
                DISABLED
                if self.is_processing
                else NORMAL
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            return

        success = bool(
            payload.get(
                "success"
            )
        )

        message = str(
            payload.get(
                "message",
                "",
            )
        )

        detail = str(
            payload.get(
                "detail",
                "",
            )
        )

        if success:

            self.postgres_connection_verified = True

            self.postgres_create_tables_button.configure(
                state=(
                    DISABLED
                    if self.is_processing
                    else NORMAL
                )
            )

            self.postgres_connection_status_var.set(
                (
                    f"{message}\n"
                    f"{detail}"
                )
            )

            self.postgres_connection_status_label.configure(
                bootstyle="success"
            )

            LOGGER.info(
                "PostgreSQL connection test succeeded."
            )

            messagebox.showinfo(
                "PostgreSQL Connection",
                (
                    "Connection successful.\n\n"
                    f"{detail}"
                ),
                parent=self.root,
            )

            return

        self.postgres_connection_verified = False

        self.postgres_create_tables_button.configure(
            state=DISABLED
        )

        self.postgres_schema_status_var.set(
            "Required tables not verified"
        )

        self.postgres_schema_status_label.configure(
            bootstyle="secondary"
        )

        self.postgres_connection_status_var.set(
            (
                f"{message}\n"
                f"{detail}"
            )
        )

        self.postgres_connection_status_label.configure(
            bootstyle="danger"
        )

        LOGGER.warning(
            "PostgreSQL connection test failed: %s",
            detail,
        )

        messagebox.showerror(
            "PostgreSQL Connection",
            (
                "Connection failed.\n\n"
                f"{detail}"
            ),
            parent=self.root,
        )

    # ========================================================
    # PostgreSQL Settings - Required Tables
    # ========================================================

    def _bind_postgres_setting_traces(
        self,
    ) -> None:
        """
        Invalidate the verified connection whenever connection input changes.

        This prevents the schema initialization button from remaining enabled
        after the user edits Host / Port / Database / User / Timeout / Password.
        """

        variables = (
            self.postgres_host_var,
            self.postgres_port_var,
            self.postgres_database_var,
            self.postgres_user_var,
            self.postgres_timeout_var,
            self.postgres_password_var,
        )

        for variable in variables:

            variable.trace_add(
                "write",
                self._on_postgres_settings_changed,
            )

    def _on_postgres_settings_changed(
        self,
        *_args: Any,
    ) -> None:

        self.postgres_connection_verified = False

        if hasattr(
            self,
            "postgres_create_tables_button",
        ):
            self.postgres_create_tables_button.configure(
                state=DISABLED
            )

        if hasattr(
            self,
            "postgres_schema_status_var",
        ):
            self.postgres_schema_status_var.set(
                "Required tables not verified"
            )

        if hasattr(
            self,
            "postgres_schema_status_label",
        ):
            self.postgres_schema_status_label.configure(
                bootstyle="secondary"
            )

    def start_postgres_schema_initialization(
        self,
    ) -> None:
        """
        Create or verify the tables required by the current ingestion tool.

        This operation is intentionally non-destructive:
            - CREATE TABLE IF NOT EXISTS
            - CREATE INDEX IF NOT EXISTS
            - no DROP
            - no TRUNCATE
            - no DELETE
        """

        if self.is_processing:
            return

        if not self.postgres_connection_verified:

            messagebox.showwarning(
                "PostgreSQL Schema",
                (
                    "Test the PostgreSQL connection successfully "
                    "before creating the required tables."
                ),
                parent=self.root,
            )

            return

        if (
            self.postgres_schema_thread
            is not None
            and self.postgres_schema_thread.is_alive()
        ):
            return

        settings = (
            self._collect_postgres_settings()
        )

        if settings is None:
            return

        password = (
            self.postgres_password_var.get()
            or os.getenv(
                "POSTGRES_PASSWORD"
            )
        )

        if not password:

            messagebox.showwarning(
                "PostgreSQL Schema",
                (
                    "The PostgreSQL password is not available. "
                    "Enter the password and test the connection again."
                ),
                parent=self.root,
            )

            self.postgres_password_entry.focus_set()

            return

        confirmed = messagebox.askyesno(
            "Create Required Tables",
            (
                "Create or verify the required PostgreSQL tables?\n\n"
                "Tables:\n"
                "  • documents\n"
                "  • chapters\n"
                "  • sections\n"
                "  • contents\n\n"
                "Existing tables and data will NOT be deleted."
            ),
            parent=self.root,
        )

        if not confirmed:
            return

        self.postgres_create_tables_button.configure(
            state=DISABLED
        )

        self.postgres_schema_status_var.set(
            "Creating / verifying required tables..."
        )

        self.postgres_schema_status_label.configure(
            bootstyle="warning"
        )

        self.postgres_schema_thread = (
            threading.Thread(
                target=(
                    self._initialize_postgres_schema_worker
                ),
                kwargs={
                    "settings": settings,
                    "password": password,
                },
                daemon=True,
                name=(
                    "postgres-schema-initializer"
                ),
            )
        )

        self.postgres_schema_thread.start()

    def _initialize_postgres_schema_worker(
        self,
        *,
        settings: PostgreSQLSettings,
        password: str,
    ) -> None:

        required_columns: dict[
            str,
            set[str],
        ] = {
            "documents": {
                "id",
                "document_id",
                "title",
                "module",
                "document_type",
                "version",
                "company",
                "category",
                "source_file",
                "language",
                "created_at",
                "updated_at",
            },
            "chapters": {
                "id",
                "document_id",
                "chapter_id",
                "title_jp",
                "title_en",
                "sort_order",
                "created_at",
                "updated_at",
            },
            "sections": {
                "id",
                "document_id",
                "chapter_id",
                "section_id",
                "title_jp",
                "title_en",
                "level",
                "sort_order",
                "parent_section_id",
                "created_at",
                "updated_at",
            },
            "contents": {
                "id",
                "document_id",
                "section_id",
                "content",
                "page_number",
                "chunk_index",
                "token_count",
                "embedding_status",
                "created_at",
                "updated_at",
            },
        }

        ddl_statements = (
            """
            CREATE TABLE IF NOT EXISTS documents
            (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(255) NOT NULL,
                title TEXT NOT NULL,
                module VARCHAR(255),
                document_type VARCHAR(50),
                version VARCHAR(50),
                company VARCHAR(200),
                category VARCHAR(200),
                source_file TEXT,
                language JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_documents_document_id
                    UNIQUE (document_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chapters
            (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(255) NOT NULL,
                chapter_id VARCHAR(50) NOT NULL,
                title_jp TEXT,
                title_en TEXT,
                sort_order INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_chapters_document_chapter
                    UNIQUE (document_id, chapter_id),
                CONSTRAINT fk_chapters_document
                    FOREIGN KEY (document_id)
                    REFERENCES documents(document_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sections
            (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(255) NOT NULL,
                chapter_id VARCHAR(50) NOT NULL,
                section_id VARCHAR(50) NOT NULL,
                title_jp TEXT,
                title_en TEXT,
                level INTEGER NOT NULL DEFAULT 2,
                sort_order INTEGER,
                parent_section_id VARCHAR(50),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_sections_document_section
                    UNIQUE (document_id, section_id),
                CONSTRAINT fk_sections_document
                    FOREIGN KEY (document_id)
                    REFERENCES documents(document_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS contents
            (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(255) NOT NULL,
                section_id VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                page_number INTEGER,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                token_count INTEGER,
                embedding_status VARCHAR(20)
                    NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_contents_document_section_chunk
                    UNIQUE (
                        document_id,
                        section_id,
                        chunk_index
                    ),
                CONSTRAINT fk_contents_document
                    FOREIGN KEY (document_id)
                    REFERENCES documents(document_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_documents_document_id
            ON documents(document_id)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_chapters_document_chapter
            ON chapters(document_id, chapter_id)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_sections_document_section
            ON sections(document_id, section_id)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                ux_contents_document_section_chunk
            ON contents(
                document_id,
                section_id,
                chunk_index
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                ix_chapters_document_id
            ON chapters(document_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                ix_sections_document_id
            ON sections(document_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                ix_sections_document_chapter
            ON sections(document_id, chapter_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                ix_contents_document_id
            ON contents(document_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                ix_contents_embedding_status
            ON contents(embedding_status)
            """,
        )

        try:
            import psycopg

            with psycopg.connect(
                host=settings.host,
                port=settings.port,
                dbname=settings.database,
                user=settings.user,
                password=password,
                connect_timeout=(
                    settings.connect_timeout
                ),
            ) as connection:

                with connection.cursor() as cursor:

                    for statement in ddl_statements:

                        cursor.execute(
                            statement
                        )

                    cursor.execute(
                        """
                        SELECT
                            table_name,
                            column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = ANY(%s)
                        """,
                        (
                            list(
                                required_columns.keys()
                            ),
                        ),
                    )

                    actual_columns: dict[
                        str,
                        set[str],
                    ] = {
                        table_name: set()
                        for table_name
                        in required_columns
                    }

                    for (
                        table_name,
                        column_name,
                    ) in cursor.fetchall():

                        if (
                            table_name
                            in actual_columns
                        ):
                            actual_columns[
                                table_name
                            ].add(
                                column_name
                            )

                    missing: list[str] = []

                    for (
                        table_name,
                        expected,
                    ) in required_columns.items():

                        missing_columns = sorted(
                            expected
                            - actual_columns[
                                table_name
                            ]
                        )

                        if missing_columns:

                            missing.append(
                                (
                                    f"{table_name}: "
                                    + ", ".join(
                                        missing_columns
                                    )
                                )
                            )

                connection.commit()

            if missing:

                self._emit(
                    "postgres_schema_result",
                    {
                        "success": False,
                        "message": (
                            "Schema verification failed"
                        ),
                        "detail": (
                            "Missing required columns:\n"
                            + "\n".join(
                                missing
                            )
                        ),
                    },
                )

                return

            self._emit(
                "postgres_schema_result",
                {
                    "success": True,
                    "message": (
                        "Required tables are ready"
                    ),
                    "detail": (
                        "documents / chapters / "
                        "sections / contents"
                    ),
                },
            )

        except Exception as exc:

            self._emit(
                "postgres_schema_result",
                {
                    "success": False,
                    "message": (
                        "Schema initialization failed"
                    ),
                    "detail": str(
                        exc
                    ),
                },
            )

    def _handle_postgres_schema_result(
        self,
        payload: Any,
    ) -> None:

        if not isinstance(
            payload,
            dict,
        ):
            return

        success = bool(
            payload.get(
                "success"
            )
        )

        message = str(
            payload.get(
                "message",
                "",
            )
        )

        detail = str(
            payload.get(
                "detail",
                "",
            )
        )

        if success:

            self.postgres_schema_status_var.set(
                (
                    f"{message}\n"
                    f"{detail}"
                )
            )

            self.postgres_schema_status_label.configure(
                bootstyle="success"
            )

            LOGGER.info(
                "PostgreSQL required tables are ready."
            )

            messagebox.showinfo(
                "PostgreSQL Schema",
                (
                    "Required tables are ready.\n\n"
                    "documents\n"
                    "chapters\n"
                    "sections\n"
                    "contents"
                ),
                parent=self.root,
            )

        else:

            self.postgres_schema_status_var.set(
                (
                    f"{message}\n"
                    f"{detail}"
                )
            )

            self.postgres_schema_status_label.configure(
                bootstyle="danger"
            )

            LOGGER.error(
                "PostgreSQL schema initialization failed: %s",
                detail,
            )

            messagebox.showerror(
                "PostgreSQL Schema",
                (
                    f"{message}.\n\n"
                    f"{detail}"
                ),
                parent=self.root,
            )

        self.postgres_create_tables_button.configure(
            state=(
                NORMAL
                if (
                    self.postgres_connection_verified
                    and not self.is_processing
                )
                else DISABLED
            )
        )

    # ========================================================
    # PostgreSQL Settings - Password Management
    # ========================================================

    def _refresh_postgres_password_status(
        self,
    ) -> None:

        available = bool(
            os.getenv(
                "POSTGRES_PASSWORD"
            )
        )

        self.postgres_password_status_var.set(
            (
                "Password available for this session"
                if available
                else (
                    "Password is not configured"
                )
            )
        )

        self.postgres_password_status_label.configure(
            bootstyle=(
                "success"
                if available
                else "warning"
            )
        )

    def clear_saved_postgres_password(
        self,
    ) -> None:

        if self.is_processing:
            return

        self.postgres_connection_verified = False

        confirmed = messagebox.askyesno(
            "Clear PostgreSQL Password",
            (
                "Remove the PostgreSQL password from "
                "this application session and from the "
                "current Windows user's saved environment?"
            ),
            parent=self.root,
        )

        if not confirmed:
            return

        os.environ.pop(
            "POSTGRES_PASSWORD",
            None,
        )

        try:
            self._delete_persisted_postgres_password()

        except OSError as exc:

            messagebox.showwarning(
                "PostgreSQL Password",
                (
                    "The password was cleared from this session, "
                    "but Windows could not remove the saved value.\n\n"
                    f"Reason: {exc}"
                ),
                parent=self.root,
            )

        self.postgres_password_var.set(
            ""
        )

        self.postgres_remember_password_var.set(
            False
        )

        self._refresh_postgres_password_status()

        self.postgres_connection_status_var.set(
            "Saved password cleared"
        )

        self.postgres_connection_status_label.configure(
            bootstyle="secondary"
        )

    @staticmethod
    def _delete_persisted_postgres_password(
    ) -> None:

        if os.name != "nt":
            return

        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                "Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:

                winreg.DeleteValue(
                    key,
                    "POSTGRES_PASSWORD",
                )

        except FileNotFoundError:
            return

        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002

            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                None,
            )

        except Exception:
            pass

    # ========================================================
    # JSON -> PostgreSQL Page
    # ========================================================

    def _build_json_import_page(
        self,
        parent: ttk.Frame,
    ) -> None:
        """
        Build the JSON -> PostgreSQL import page.

        This page imports JSON files generated by this application.
        It does not re-run PDF / DOCX / PPTX / XLSX parsing.
        """

        workspace = ttk.Frame(
            parent
        )

        workspace.pack(
            fill=BOTH,
            expand=True,
        )

        workspace.columnconfigure(
            0,
            weight=5,
            uniform="json-columns",
        )

        workspace.columnconfigure(
            1,
            weight=4,
            uniform="json-columns",
        )

        workspace.columnconfigure(
            2,
            weight=5,
            uniform="json-columns",
        )

        workspace.rowconfigure(
            0,
            weight=1,
        )

        left_panel = ttk.Frame(
            workspace
        )

        left_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(
                0,
                8,
            ),
        )

        center_panel = ttk.Frame(
            workspace
        )

        center_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=8,
        )

        right_panel = ttk.Frame(
            workspace
        )

        right_panel.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(
                8,
                0,
            ),
        )

        self._build_json_file_section(
            left_panel
        )

        self._build_json_import_info_section(
            center_panel
        )

        self._build_json_import_action_section(
            center_panel
        )

        self._build_json_import_progress_section(
            right_panel
        )

        self._build_json_import_log_section(
            right_panel
        )

    def _build_json_file_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="1. JSON Files",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        toolbar = ttk.Frame(
            frame
        )

        toolbar.pack(
            fill=X,
            pady=(
                0,
                10,
            ),
        )

        self.add_json_files_button = (
            ttk.Button(
                toolbar,
                text="＋  Add JSON",
                command=(
                    self.select_json_files
                ),
                bootstyle="primary",
            )
        )

        self.add_json_files_button.pack(
            side=LEFT
        )

        self.remove_json_files_button = (
            ttk.Button(
                toolbar,
                text="Remove",
                command=(
                    self.remove_selected_json_files
                ),
                bootstyle="secondary-outline",
            )
        )

        self.remove_json_files_button.pack(
            side=LEFT,
            padx=(
                8,
                0,
            ),
        )

        self.clear_json_files_button = (
            ttk.Button(
                toolbar,
                text="Clear",
                command=(
                    self.clear_json_files
                ),
                bootstyle="secondary-outline",
            )
        )

        self.clear_json_files_button.pack(
            side=LEFT,
            padx=(
                8,
                0,
            ),
        )

        list_container = ttk.Frame(
            frame
        )

        list_container.pack(
            fill=BOTH,
            expand=True,
        )

        self.json_file_listbox = tk.Listbox(
            list_container,
            height=24,
            selectmode=EXTENDED,
            activestyle="none",
            font=(
                "Segoe UI",
                10,
            ),
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            selectborderwidth=0,
        )

        scrollbar = ttk.Scrollbar(
            list_container,
            orient=VERTICAL,
            command=(
                self.json_file_listbox
                .yview
            ),
            bootstyle="round",
        )

        self.json_file_listbox.configure(
            yscrollcommand=(
                scrollbar.set
            )
        )

        self.json_file_listbox.pack(
            side=LEFT,
            fill=BOTH,
            expand=True,
        )

        scrollbar.pack(
            side=RIGHT,
            fill=Y,
        )

        footer = ttk.Frame(
            frame
        )

        footer.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        ttk.Label(
            footer,
            text=(
                "Only JSON generated by "
                "Document Ingestion Platform"
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            side=LEFT
        )

        ttk.Label(
            footer,
            textvariable=(
                self.json_file_count_var
            ),
            bootstyle="primary",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            side=RIGHT
        )

    def _build_json_import_info_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        target_frame = ttk.LabelFrame(
            parent,
            text="2. Import Target",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        target_frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        ttk.Label(
            target_frame,
            text="PostgreSQL",
            font=(
                "Segoe UI",
                11,
                "bold",
            ),
            bootstyle="dark",
        ).pack(
            anchor="w"
        )

        ttk.Label(
            target_frame,
            text=(
                "Database connection settings are loaded "
                "from config.yaml. The password is requested "
                "only when it is not already available."
            ),
            wraplength=330,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w",
            pady=(
                8,
                0,
            ),
        )

        behavior_frame = ttk.LabelFrame(
            parent,
            text="3. Import Behavior",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        behavior_frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        ttk.Label(
            behavior_frame,
            text="What happens during import",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            pady=(
                0,
                8,
            ),
        )

        for text in (
            "• Validate the JSON structure",
            "• Rebuild the Unified Document Model",
            "• Reuse the existing PostgresStorage",
            "• Update the same document_id idempotently",
            "• Contents are stored with embedding_status=PENDING",
        ):
            ttk.Label(
                behavior_frame,
                text=text,
                wraplength=330,
                justify=LEFT,
                bootstyle="secondary",
                style="Small.TLabel",
            ).pack(
                anchor="w",
                pady=(
                    2,
                    0,
                ),
            )

    def _build_json_import_action_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="4. Actions",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
        )

        self.import_json_button = (
            ttk.Button(
                frame,
                text="⇩  Import to PostgreSQL",
                command=(
                    self.start_json_import
                ),
                bootstyle="success",
            )
        )

        self.import_json_button.pack(
            fill=X,
            ipady=5,
        )

        self.cancel_json_import_button = (
            ttk.Button(
                frame,
                text="Cancel",
                command=(
                    self.cancel_json_import
                ),
                state=DISABLED,
                bootstyle="danger-outline",
            )
        )

        self.cancel_json_import_button.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        ttk.Label(
            frame,
            text=(
                "Import does not parse the original Office/PDF "
                "file again."
            ),
            wraplength=330,
            justify=LEFT,
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w",
            pady=(
                12,
                0,
            ),
        )

    def _build_json_import_progress_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="5. Import Status",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        header = ttk.Frame(
            frame
        )

        header.pack(
            fill=X
        )

        ttk.Label(
            header,
            textvariable=(
                self.json_import_status_var
            ),
            style="StatusBold.TLabel",
            bootstyle="dark",
        ).pack(
            side=LEFT
        )

        ttk.Label(
            header,
            textvariable=(
                self.json_import_progress_text_var
            ),
            bootstyle="success",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side=RIGHT
        )

        self.json_import_progress_bar = (
            ttk.Progressbar(
                frame,
                variable=(
                    self.json_import_progress_var
                ),
                maximum=100,
                bootstyle="success-striped",
            )
        )

        self.json_import_progress_bar.pack(
            fill=X,
            pady=(
                12,
                10,
            ),
        )

        ttk.Label(
            frame,
            textvariable=(
                self.json_import_current_file_var
            ),
            wraplength=400,
            justify=LEFT,
            bootstyle="secondary",
        ).pack(
            anchor="w",
            pady=(
                0,
                8,
            ),
        )

        ttk.Separator(
            frame,
            orient="horizontal",
            bootstyle="secondary",
        ).pack(
            fill=X,
            pady=(
                2,
                8,
            ),
        )

        ttk.Label(
            frame,
            textvariable=(
                self.json_import_summary_var
            ),
            bootstyle="secondary",
            style="Small.TLabel",
        ).pack(
            anchor="w"
        )

    def _build_json_import_log_section(
        self,
        parent: ttk.Frame,
    ) -> None:

        frame = ttk.LabelFrame(
            parent,
            text="Import Log",
            padding=14,
            style="Card.TLabelframe",
            bootstyle="secondary",
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        text_container = ttk.Frame(
            frame
        )

        text_container.pack(
            fill=BOTH,
            expand=True,
        )

        self.json_import_log_text = tk.Text(
            text_container,
            state=DISABLED,
            wrap=WORD,
            height=20,
            font=(
                "Cascadia Mono",
                9,
            ),
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )

        scrollbar = ttk.Scrollbar(
            text_container,
            orient=VERTICAL,
            command=(
                self.json_import_log_text
                .yview
            ),
            bootstyle="round",
        )

        self.json_import_log_text.configure(
            yscrollcommand=(
                scrollbar.set
            )
        )

        self.json_import_log_text.pack(
            side=LEFT,
            fill=BOTH,
            expand=True,
        )

        scrollbar.pack(
            side=RIGHT,
            fill=Y,
        )

    # ========================================================
    # JSON File Selection
    # ========================================================

    def select_json_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        raw_files = (
            filedialog.askopenfilenames(
                title=(
                    "Select Document Ingestion JSON"
                ),
                filetypes=JSON_FILE_TYPES,
            )
        )

        if not raw_files:
            return

        existing_paths = {
            str(
                path.resolve()
            ).lower()
            for path
            in self.selected_json_files
        }

        added = 0

        for raw_file in raw_files:
            path = Path(
                raw_file
            ).resolve()

            if path.suffix.lower() != ".json":
                continue

            normalized = str(
                path
            ).lower()

            if normalized in existing_paths:
                continue

            self.selected_json_files.append(
                path
            )

            self.json_file_listbox.insert(
                END,
                str(
                    path
                ),
            )

            existing_paths.add(
                normalized
            )

            added += 1

        self._update_json_file_count()

        if added == 0:
            LOGGER.info(
                "No new JSON files added."
            )

    def remove_selected_json_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        indexes = list(
            self.json_file_listbox
            .curselection()
        )

        for index in reversed(
            indexes
        ):
            self.json_file_listbox.delete(
                index
            )

            del self.selected_json_files[
                index
            ]

        self._update_json_file_count()

    def clear_json_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        self.selected_json_files.clear()

        self.json_file_listbox.delete(
            0,
            END,
        )

        self._update_json_file_count()

    def _update_json_file_count(
        self,
    ) -> None:

        count = len(
            self.selected_json_files
        )

        text = (
            f"{count} JSON file selected"
            if count == 1
            else (
                f"{count} JSON files selected"
            )
        )

        self.json_file_count_var.set(
            text
        )

    # ========================================================
    # JSON -> Document
    # ========================================================

    @staticmethod
    def _load_document_from_json(
        json_path: Path,
    ) -> Document:
        """
        Rebuild a Document from JSON generated by JsonBuilder.

        JsonBuilder stores:
            document
            metadata
            chapters
            sections
            contents

        pages / raw blocks are not required by PostgresStorage,
        therefore they are intentionally reconstructed as empty lists.
        """

        try:
            with json_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                payload = json.load(
                    file
                )

        except json.JSONDecodeError as exc:
            raise ValueError(
                "Invalid JSON syntax: "
                f"{exc}"
            ) from exc

        except OSError as exc:
            raise ValueError(
                "Unable to read JSON file: "
                f"{exc}"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "JSON root must be an object."
            )

        document_data = payload.get(
            "document"
        )

        if not isinstance(
            document_data,
            dict,
        ):
            raise ValueError(
                "Missing or invalid 'document' object."
            )

        file_name = document_data.get(
            "file_name"
        )

        file_type = document_data.get(
            "file_type"
        )

        document_id = document_data.get(
            "document_id"
        )

        if (
            not isinstance(
                file_name,
                str,
            )
            or not file_name.strip()
        ):
            raise ValueError(
                "document.file_name is missing."
            )

        if (
            not isinstance(
                file_type,
                str,
            )
            or not file_type.strip()
        ):
            raise ValueError(
                "document.file_type is missing."
            )

        metadata = payload.get(
            "metadata",
            {},
        )

        if metadata is None:
            metadata = {}

        if not isinstance(
            metadata,
            dict,
        ):
            raise ValueError(
                "'metadata' must be an object."
            )

        # Work on a new dictionary so the parsed JSON is never mutated.
        metadata = dict(
            metadata
        )

        if (
            isinstance(
                document_id,
                str,
            )
            and document_id.strip()
        ):
            metadata[
                "document_id"
            ] = document_id.strip()

        chapters_data = payload.get(
            "chapters",
            [],
        )

        sections_data = payload.get(
            "sections",
            [],
        )

        contents_data = payload.get(
            "contents",
            [],
        )

        for key, value in (
            (
                "chapters",
                chapters_data,
            ),
            (
                "sections",
                sections_data,
            ),
            (
                "contents",
                contents_data,
            ),
        ):
            if not isinstance(
                value,
                list,
            ):
                raise ValueError(
                    f"'{key}' must be an array."
                )

        chapters = [
            Chapter.model_validate(
                record
            )
            for record
            in chapters_data
        ]

        sections = [
            Section.model_validate(
                record
            )
            for record
            in sections_data
        ]

        contents = [
            Content.model_validate(
                record
            )
            for record
            in contents_data
        ]

        if not contents:
            raise ValueError(
                "JSON contains no contents."
            )

        return Document(
            file_name=(
                file_name.strip()
            ),
            file_type=(
                file_type.strip().lower()
            ),
            pages=[],
            blocks=[],
            chapters=chapters,
            sections=sections,
            contents=contents,
            metadata=metadata,
        )

    # ========================================================
    # JSON Import Start / Worker
    # ========================================================

    def start_json_import(
        self,
    ) -> None:

        if self.is_processing:
            return

        if not self.selected_json_files:
            messagebox.showwarning(
                "No JSON Files",
                (
                    "Please select at least "
                    "one JSON file."
                ),
            )

            return

        missing_files = [
            path
            for path
            in self.selected_json_files
            if not path.is_file()
        ]

        if missing_files:
            messagebox.showerror(
                "Missing JSON Files",
                (
                    "Some selected JSON files "
                    "no longer exist:\n\n"
                    + "\n".join(
                        str(
                            path
                        )
                        for path
                        in missing_files[:10]
                    )
                ),
            )

            return

        if not self._ensure_postgres_password():
            return

        files = list(
            self.selected_json_files
        )

        self.is_processing = True
        self.cancel_requested.clear()
        self.json_import_failures.clear()

        self._set_controls_enabled(
            False
        )

        self.cancel_json_import_button.configure(
            state=NORMAL
        )

        self.json_import_progress_var.set(
            0
        )

        self.json_import_progress_text_var.set(
            "0%"
        )

        self.json_import_status_var.set(
            "Importing"
        )

        self.json_import_current_file_var.set(
            "Preparing JSON import..."
        )

        self.json_import_summary_var.set(
            (
                "Success: 0    "
                "Failed: 0    "
                f"Total: {len(files)}"
            )
        )

        self._clear_json_import_log()

        LOGGER.info(
            "JSON import started | "
            "total=%s",
            len(
                files
            ),
        )

        self.json_import_thread = (
            threading.Thread(
                target=(
                    self._import_json_files
                ),
                kwargs={
                    "files": files,
                },
                daemon=True,
                name=(
                    "json-postgres-import-worker"
                ),
            )
        )

        self.json_import_thread.start()

    def _import_json_files(
        self,
        *,
        files: list[Path],
    ) -> None:

        success_count = 0
        failed_count = 0
        total = len(
            files
        )

        cancelled = False

        # Create the storage after the PostgreSQL password has been
        # made available to the current process.
        storage = PostgresStorage()

        for index, json_path in enumerate(
            files,
            start=1,
        ):

            if self.cancel_requested.is_set():
                cancelled = True
                break

            self._emit(
                "json_import_current_file",
                (
                    f"{index}/{total} "
                    f"{json_path.name}"
                ),
            )

            self._emit(
                "json_import_log",
                (
                    "START   | "
                    f"{json_path.name}"
                ),
            )

            try:
                document = (
                    self._load_document_from_json(
                        json_path
                    )
                )

                storage.save(
                    document
                )

                success_count += 1

                success_message = (
                    "SUCCESS | "
                    f"{json_path.name} | "
                    f"chapters="
                    f"{len(document.chapters)} | "
                    f"sections="
                    f"{len(document.sections)} | "
                    f"contents="
                    f"{len(document.contents)}"
                )

                self._emit(
                    "json_import_log",
                    success_message,
                )

                LOGGER.info(
                    "JSON import succeeded | "
                    "file=%s | "
                    "chapters=%s | "
                    "sections=%s | "
                    "contents=%s",
                    json_path,
                    len(
                        document.chapters
                    ),
                    len(
                        document.sections
                    ),
                    len(
                        document.contents
                    ),
                )

            except Exception as exc:

                failed_count += 1

                failure = FileFailure(
                    file_path=json_path,
                    error_type=(
                        type(
                            exc
                        ).__name__
                    ),
                    error_message=str(
                        exc
                    ),
                )

                self.json_import_failures.append(
                    failure
                )

                self._emit(
                    "json_import_log",
                    (
                        "FAILED  | "
                        f"{json_path.name} | "
                        f"{failure.error_type}: "
                        f"{failure.error_message}"
                    ),
                )

                LOGGER.error(
                    "JSON import failed | "
                    "file=%s | "
                    "error_type=%s | "
                    "error=%s\n%s",
                    json_path,
                    failure.error_type,
                    failure.error_message,
                    traceback.format_exc(),
                )

            percentage = int(
                index
                / total
                * 100
            )

            self._emit(
                "json_import_progress",
                percentage,
            )

            self._emit(
                "json_import_summary",
                BatchSummary(
                    success=success_count,
                    failed=failed_count,
                    total=total,
                    cancelled=False,
                ),
            )

        self._emit(
            "json_import_finished",
            BatchSummary(
                success=success_count,
                failed=failed_count,
                total=total,
                cancelled=cancelled,
            ),
        )

    def cancel_json_import(
        self,
    ) -> None:

        if not self.is_processing:
            return

        if self.cancel_requested.is_set():
            return

        confirmed = messagebox.askyesno(
            "Cancel JSON Import",
            (
                "Stop after the current "
                "JSON file finishes?"
            ),
        )

        if not confirmed:
            return

        self.cancel_requested.set()

        self.cancel_json_import_button.configure(
            state=DISABLED
        )

        self.json_import_status_var.set(
            "Cancelling..."
        )

        self._append_json_import_log(
            (
                "CANCEL  | "
                "Cancellation requested."
            )
        )

    # ========================================================
    # JSON Import Log / Summary / Finish
    # ========================================================

    def _append_json_import_log(
        self,
        message: str,
    ) -> None:

        self.json_import_log_text.configure(
            state=NORMAL
        )

        self.json_import_log_text.insert(
            END,
            message + "\n",
        )

        self.json_import_log_text.see(
            END
        )

        self.json_import_log_text.configure(
            state=DISABLED
        )

    def _clear_json_import_log(
        self,
    ) -> None:

        self.json_import_log_text.configure(
            state=NORMAL
        )

        self.json_import_log_text.delete(
            "1.0",
            END,
        )

        self.json_import_log_text.configure(
            state=DISABLED
        )

    def _update_json_import_summary(
        self,
        summary: BatchSummary,
    ) -> None:

        self.json_import_summary_var.set(
            (
                f"Success: "
                f"{summary.success}    "
                f"Failed: "
                f"{summary.failed}    "
                f"Total: "
                f"{summary.total}"
            )
        )

    def _handle_json_import_finished(
        self,
        summary: BatchSummary,
    ) -> None:

        self.is_processing = False
        self.cancel_requested.clear()

        self._set_controls_enabled(
            True
        )

        self.cancel_json_import_button.configure(
            state=DISABLED
        )

        self._update_json_import_summary(
            summary
        )

        if summary.cancelled:

            self.json_import_status_var.set(
                "Cancelled"
            )

            self.json_import_current_file_var.set(
                "JSON import was cancelled."
            )

            self._append_json_import_log(
                (
                    "BATCH   | "
                    "JSON import cancelled."
                )
            )

            messagebox.showwarning(
                "JSON Import Cancelled",
                (
                    "JSON import was cancelled."
                ),
            )

            return

        self.json_import_progress_var.set(
            100
        )

        self.json_import_progress_text_var.set(
            "100%"
        )

        if summary.failed == 0:

            self.json_import_status_var.set(
                "Completed"
            )

            self.json_import_current_file_var.set(
                (
                    "All JSON files were imported "
                    "to PostgreSQL."
                )
            )

            self._append_json_import_log(
                (
                    "BATCH   | "
                    f"success={summary.success} | "
                    "failed=0 | "
                    f"total={summary.total}"
                )
            )

            messagebox.showinfo(
                "JSON Import Completed",
                (
                    "All JSON files were imported "
                    "successfully.\n\n"
                    f"Success: {summary.success}\n"
                    "Failed: 0\n"
                    f"Total: {summary.total}"
                ),
            )

            return

        self.json_import_status_var.set(
            "Completed with Errors"
        )

        self.json_import_current_file_var.set(
            (
                "JSON import completed "
                "with errors."
            )
        )

        lines = [
            "JSON import completed with errors.",
            "",
            f"Success: {summary.success}",
            f"Failed: {summary.failed}",
            f"Total: {summary.total}",
            "",
            "Failed JSON files:",
        ]

        for index, failure in enumerate(
            self.json_import_failures[:5],
            start=1,
        ):
            lines.extend(
                [
                    "",
                    (
                        f"{index}. "
                        f"{failure.file_path.name}"
                    ),
                    (
                        "   "
                        f"{failure.error_type}: "
                        f"{failure.error_message}"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "Full exception details:",
                str(
                    LOG_DIR
                    / "gui.log"
                ),
            ]
        )

        messagebox.showwarning(
            "JSON Import Completed with Errors",
            "\n".join(
                lines
            ),
        )

    def select_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        raw_files = (
            filedialog
            .askopenfilenames(
                title=(
                    "Select Documents"
                ),
                filetypes=(
                    SUPPORTED_FILE_TYPES
                ),
            )
        )

        if not raw_files:
            return

        existing_paths = {
            str(
                path.resolve()
            ).lower()
            for path
            in self.selected_files
        }

        added = 0

        unsupported: list[
            str
        ] = []

        for raw_file in raw_files:

            path = Path(
                raw_file
            ).resolve()

            if (
                path.suffix.lower()
                not in SUPPORTED_SUFFIXES
            ):
                unsupported.append(
                    path.name
                )

                continue

            normalized = str(
                path
            ).lower()

            if normalized in existing_paths:
                continue

            self.selected_files.append(
                path
            )

            self.file_listbox.insert(
                END,
                str(
                    path
                ),
            )

            existing_paths.add(
                normalized
            )

            added += 1

        self._update_file_count()

        if unsupported:

            messagebox.showwarning(
                "Unsupported Files",
                (
                    "The following files "
                    "were ignored:\n\n"
                    + "\n".join(
                        unsupported[:10]
                    )
                ),
            )

        if added == 0:

            LOGGER.info(
                "No new input files added."
            )

    def remove_selected_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        indexes = list(
            self.file_listbox
            .curselection()
        )

        for index in reversed(
            indexes
        ):

            self.file_listbox.delete(
                index
            )

            del self.selected_files[
                index
            ]

        self._update_file_count()

    def clear_files(
        self,
    ) -> None:

        if self.is_processing:
            return

        self.selected_files.clear()

        self.file_listbox.delete(
            0,
            END,
        )

        self._update_file_count()

    def _update_file_count(
        self,
    ) -> None:

        count = len(
            self.selected_files
        )

        text = (
            f"{count} file selected"
            if count == 1
            else (
                f"{count} files selected"
            )
        )

        self.file_count_var.set(
            text
        )

    # ========================================================
    # Output Directory
    # ========================================================

    def select_output_directory(
        self,
    ) -> None:

        if self.is_processing:
            return

        current_value = (
            self.output_directory_var
            .get()
            .strip()
        )

        initial_dir = None

        if current_value:

            current_path = Path(
                current_value
            )

            if current_path.exists():
                initial_dir = str(
                    current_path
                )

        selected = (
            filedialog
            .askdirectory(
                title=(
                    "Select Output Directory"
                ),
                initialdir=(
                    initial_dir
                ),
            )
        )

        if not selected:
            return

        self.output_directory_var.set(
            selected
        )

    # ========================================================
    # PostgreSQL Credentials
    # ========================================================

    def _ensure_postgres_password(self) -> bool:
        """
        Ensure POSTGRES_PASSWORD is available for this process.

        If the environment variable already exists, no dialog is shown.
        Otherwise a masked GUI dialog requests the password. The password
        is never written to the application log or configuration file.
        """

        existing_password = os.getenv(
            "POSTGRES_PASSWORD"
        )

        if existing_password:
            return True

        result = self._show_postgres_password_dialog()

        if result is None:
            return False

        password, remember = result

        # Make the credential immediately available to the current EXE /
        # Python process. This is required even when it is persisted below.
        os.environ["POSTGRES_PASSWORD"] = password

        if remember:
            try:
                self._persist_postgres_password(
                    password
                )
            except OSError as exc:
                LOGGER.warning(
                    "Unable to persist PostgreSQL password: %s",
                    exc,
                )

                messagebox.showwarning(
                    "PostgreSQL Password",
                    (
                        "The password will be used for this session, "
                        "but Windows could not save it for future runs.\n\n"
                        f"Reason: {exc}"
                    ),
                    parent=self.root,
                )

        if hasattr(
            self,
            "postgres_password_status_label",
        ):
            self._refresh_postgres_password_status()

        return True

    def _show_postgres_password_dialog(
        self,
    ) -> tuple[str, bool] | None:
        """
        Display a modal masked PostgreSQL password dialog.

        Returns:
            (password, remember) when confirmed.
            None when cancelled.
        """

        dialog = tk.Toplevel(
            self.root
        )

        dialog.title(
            "PostgreSQL Password"
        )

        dialog.resizable(
            False,
            False,
        )

        dialog.transient(
            self.root
        )

        password_var = tk.StringVar()
        remember_var = tk.BooleanVar(
            value=False
        )

        result: dict[
            str,
            tuple[str, bool] | None,
        ] = {
            "value": None
        }

        frame = ttk.Frame(
            dialog,
            padding=20,
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        ttk.Label(
            frame,
            text=(
                "PostgreSQL output is enabled.\n"
                "Enter the PostgreSQL password."
            ),
        ).pack(
            anchor="w",
            pady=(0, 12),
        )

        ttk.Label(
            frame,
            text="Password",
        ).pack(
            anchor="w"
        )

        password_entry = ttk.Entry(
            frame,
            textvariable=password_var,
            show="*",
            width=42,
        )

        password_entry.pack(
            fill=X,
            pady=(4, 12),
        )

        ttk.Checkbutton(
            frame,
            text="Remember on this computer",
            variable=remember_var,
        ).pack(
            anchor="w"
        )

        button_frame = ttk.Frame(
            frame
        )

        button_frame.pack(
            fill=X,
            pady=(18, 0),
        )

        def cancel() -> None:
            result["value"] = None
            dialog.destroy()

        def confirm() -> None:
            password = password_var.get()

            if not password:
                messagebox.showwarning(
                    "PostgreSQL Password",
                    "Please enter the PostgreSQL password.",
                    parent=dialog,
                )
                password_entry.focus_set()
                return

            result["value"] = (
                password,
                bool(remember_var.get()),
            )

            dialog.destroy()

        ttk.Button(
            button_frame,
            text="Cancel",
            command=cancel,
        ).pack(
            side=RIGHT,
        )

        ttk.Button(
            button_frame,
            text="OK",
            command=confirm,
        ).pack(
            side=RIGHT,
            padx=(0, 10),
        )

        dialog.protocol(
            "WM_DELETE_WINDOW",
            cancel,
        )

        dialog.bind(
            "<Return>",
            lambda _event: confirm(),
        )

        dialog.bind(
            "<Escape>",
            lambda _event: cancel(),
        )

        dialog.update_idletasks()

        x = (
            self.root.winfo_rootx()
            + max(
                0,
                (
                    self.root.winfo_width()
                    - dialog.winfo_width()
                ) // 2,
            )
        )

        y = (
            self.root.winfo_rooty()
            + max(
                0,
                (
                    self.root.winfo_height()
                    - dialog.winfo_height()
                ) // 2,
            )
        )

        dialog.geometry(
            f"+{x}+{y}"
        )

        dialog.grab_set()
        password_entry.focus_set()
        self.root.wait_window(
            dialog
        )

        return result["value"]

    @staticmethod
    def _persist_postgres_password(
        password: str,
    ) -> None:
        """
        Persist POSTGRES_PASSWORD in the current Windows user's environment.

        The value is stored under HKCU\\Environment, so administrator
        privileges are not required.
        """

        if os.name != "nt":
            raise OSError(
                "Remember password is supported only on Windows."
            )

        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                "POSTGRES_PASSWORD",
                0,
                winreg.REG_SZ,
                password,
            )

        # Notify the Windows shell that the user environment changed so
        # subsequently launched processes can receive the new value.
        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002

            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                None,
            )
        except Exception:
            # Persistence already succeeded; notification failure is not
            # fatal for the current process.
            pass

    # ========================================================
    # Validation
    # ========================================================

    def _validate_before_start(
        self,
    ) -> ProcessingOptions | None:

        if not self.selected_files:

            messagebox.showwarning(
                "No Input Files",
                (
                    "Please select at least "
                    "one document."
                ),
            )

            return None

        missing_files = [
            path
            for path
            in self.selected_files
            if not path.is_file()
        ]

        if missing_files:

            messagebox.showerror(
                "Missing Input Files",
                (
                    "Some selected files "
                    "no longer exist:\n\n"
                    + "\n".join(
                        str(
                            path
                        )
                        for path
                        in missing_files[:10]
                    )
                ),
            )

            return None

        save_json = bool(
            self.save_json_var.get()
        )

        save_database = bool(
            self.save_database_var.get()
        )

        if (
            not save_json
            and not save_database
        ):

            messagebox.showwarning(
                "No Output Selected",
                (
                    "Enable at least one "
                    "processing output."
                ),
            )

            return None

        output_text = (
            self.output_directory_var
            .get()
            .strip()
        )

        if not output_text:

            messagebox.showwarning(
                "Output Directory",
                (
                    "Please select an "
                    "output directory."
                ),
            )

            return None

        output_directory = Path(
            output_text
        ).resolve()

        try:

            output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        except OSError as exc:

            messagebox.showerror(
                "Output Directory Error",
                (
                    "Unable to access or "
                    "create output directory.\n\n"
                    f"{exc}"
                ),
            )

            return None

        if save_database:

            if not self._ensure_postgres_password():
                return None

        return ProcessingOptions(
            output_directory=(
                output_directory
            ),
            save_json=(
                save_json
            ),
            save_database=(
                save_database
            ),
        )

    # ========================================================
    # Start Processing
    # ========================================================

    def start_processing(
        self,
    ) -> None:

        if self.is_processing:
            return

        options = (
            self._validate_before_start()
        )

        if options is None:
            return

        files = list(
            self.selected_files
        )

        self.cancel_requested.clear()

        self.failures.clear()

        self._prepare_processing_ui(
            total=len(
                files
            )
        )

        LOGGER.info(
            (
                "Batch started | "
                "total=%s | "
                "json=%s | "
                "postgresql=%s | "
                "output=%s"
            ),
            len(files),
            options.save_json,
            options.save_database,
            options.output_directory,
        )

        self.processing_thread = (
            threading.Thread(
                target=(
                    self._process_files
                ),
                kwargs={
                    "files": files,
                    "options": options,
                },
                daemon=True,
                name=(
                    "document-ingestion-worker"
                ),
            )
        )

        self.processing_thread.start()

    def _prepare_processing_ui(
        self,
        *,
        total: int,
    ) -> None:

        self.is_processing = True

        self._set_controls_enabled(
            False
        )

        self.cancel_button.configure(
            state=NORMAL
        )

        self.progress_var.set(
            0
        )

        self.progress_text_var.set(
            "0%"
        )

        self.status_var.set(
            "Processing"
        )

        self.current_file_var.set(
            "Preparing batch..."
        )

        self.summary_var.set(
            (
                "Success: 0    "
                "Failed: 0    "
                f"Total: {total}"
            )
        )

        self._clear_log()

    # ========================================================
    # Worker Thread
    # ========================================================

    def _process_files(
        self,
        *,
        files: list[Path],
        options: ProcessingOptions,
    ) -> None:

        success_count = 0
        failed_count = 0

        total = len(
            files
        )

        cancelled = False

        for index, file_path in enumerate(
            files,
            start=1,
        ):

            if self.cancel_requested.is_set():

                cancelled = True

                LOGGER.warning(
                    "Batch cancellation requested."
                )

                break

            self._emit(
                "current_file",
                (
                    f"{index}/{total} "
                    f"{file_path.name}"
                ),
            )

            self._emit(
                "log",
                (
                    f"START   | "
                    f"{file_path.name}"
                ),
            )

            LOGGER.info(
                "Processing started | "
                "file=%s",
                file_path,
            )

            try:

                pipeline = (
                    PipelineFactory.create(
                        file_path,
                        save_json=(
                            options.save_json
                        ),
                        save_database=(
                            options
                            .save_database
                        ),
                    )
                )

                output_path = (
                    options
                    .output_directory
                    / (
                        f"{file_path.stem}"
                        ".json"
                    )
                )

                document = (
                    pipeline.run(
                        file_path=(
                            file_path
                        ),
                        output=(
                            output_path
                        ),
                    )
                )

                success_count += 1

                pages = len(
                    getattr(
                        document,
                        "pages",
                        [],
                    )
                )

                chapters = len(
                    getattr(
                        document,
                        "chapters",
                        [],
                    )
                )

                sections = len(
                    getattr(
                        document,
                        "sections",
                        [],
                    )
                )

                contents = len(
                    getattr(
                        document,
                        "contents",
                        [],
                    )
                )

                success_message = (
                    "SUCCESS | "
                    f"{file_path.name} | "
                    f"pages={pages} | "
                    f"chapters={chapters} | "
                    f"sections={sections} | "
                    f"contents={contents}"
                )

                self._emit(
                    "log",
                    success_message,
                )

                LOGGER.info(
                    success_message
                )

            except Exception as exc:

                failed_count += 1

                error_type = (
                    type(
                        exc
                    ).__name__
                )

                error_message = str(
                    exc
                )

                failure = FileFailure(
                    file_path=(
                        file_path
                    ),
                    error_type=(
                        error_type
                    ),
                    error_message=(
                        error_message
                    ),
                )

                self.failures.append(
                    failure
                )

                gui_message = (
                    "FAILED  | "
                    f"{file_path.name} | "
                    f"{error_type}: "
                    f"{error_message}"
                )

                self._emit(
                    "log",
                    gui_message,
                )

                LOGGER.error(
                    gui_message
                )

                LOGGER.error(
                    "Traceback | "
                    "file=%s\n%s",
                    file_path,
                    traceback.format_exc(),
                )

            percentage = int(
                index
                / total
                * 100
            )

            self._emit(
                "progress",
                percentage,
            )

            self._emit(
                "summary",
                BatchSummary(
                    success=(
                        success_count
                    ),
                    failed=(
                        failed_count
                    ),
                    total=total,
                    cancelled=False,
                ),
            )

        self._emit(
            "finished",
            BatchSummary(
                success=(
                    success_count
                ),
                failed=(
                    failed_count
                ),
                total=total,
                cancelled=(
                    cancelled
                ),
            ),
        )

    # ========================================================
    # Cancel
    # ========================================================

    def cancel_processing(
        self,
    ) -> None:

        if not self.is_processing:
            return

        if self.cancel_requested.is_set():
            return

        confirmed = (
            messagebox.askyesno(
                "Cancel Processing",
                (
                    "Stop after the current "
                    "document finishes?"
                ),
            )
        )

        if not confirmed:
            return

        self.cancel_requested.set()

        self.cancel_button.configure(
            state=DISABLED
        )

        self.status_var.set(
            "Cancelling..."
        )

        self._append_log(
            (
                "CANCEL  | "
                "Cancellation requested."
            )
        )

    # ========================================================
    # Event Queue
    # ========================================================

    def _emit(
        self,
        event_type: str,
        payload: Any,
    ) -> None:

        self.event_queue.put(
            (
                event_type,
                payload,
            )
        )

    def _poll_events(
        self,
    ) -> None:

        try:

            while True:

                (
                    event_type,
                    payload,
                ) = (
                    self.event_queue
                    .get_nowait()
                )

                self._handle_event(
                    event_type,
                    payload,
                )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self._poll_events,
        )

    def _handle_event(
        self,
        event_type: str,
        payload: Any,
    ) -> None:

        if event_type == "log":

            self._append_log(
                str(
                    payload
                )
            )

        elif (
            event_type
            == "current_file"
        ):

            self.current_file_var.set(
                str(
                    payload
                )
            )

        elif (
            event_type
            == "progress"
        ):

            value = float(
                payload
            )

            self.progress_var.set(
                value
            )

            self.progress_text_var.set(
                f"{int(value)}%"
            )

        elif (
            event_type
            == "summary"
        ):

            self._update_summary(
                payload
            )

        elif (
            event_type
            == "finished"
        ):

            self._handle_finished(
                payload
            )

        elif (
            event_type
            == "json_import_log"
        ):

            self._append_json_import_log(
                str(
                    payload
                )
            )

        elif (
            event_type
            == "json_import_current_file"
        ):

            self.json_import_current_file_var.set(
                str(
                    payload
                )
            )

        elif (
            event_type
            == "json_import_progress"
        ):

            value = float(
                payload
            )

            self.json_import_progress_var.set(
                value
            )

            self.json_import_progress_text_var.set(
                f"{int(value)}%"
            )

        elif (
            event_type
            == "json_import_summary"
        ):

            self._update_json_import_summary(
                payload
            )

        elif (
            event_type
            == "json_import_finished"
        ):

            self._handle_json_import_finished(
                payload
            )

        elif (
            event_type
            == "postgres_test_result"
        ):

            self._handle_postgres_test_result(
                payload
            )

        elif (
            event_type
            == "postgres_schema_result"
        ):

            self._handle_postgres_schema_result(
                payload
            )

    # ========================================================
    # Summary
    # ========================================================

    def _update_summary(
        self,
        summary: BatchSummary,
    ) -> None:

        self.summary_var.set(
            (
                f"Success: "
                f"{summary.success}    "
                f"Failed: "
                f"{summary.failed}    "
                f"Total: "
                f"{summary.total}"
            )
        )

    # ========================================================
    # Finish
    # ========================================================

    def _handle_finished(
        self,
        summary: BatchSummary,
    ) -> None:

        self.is_processing = False

        self.cancel_requested.clear()

        self._set_controls_enabled(
            True
        )

        self.cancel_button.configure(
            state=DISABLED
        )

        self._update_summary(
            summary
        )

        if summary.cancelled:

            self.status_var.set(
                "Cancelled"
            )

            self.current_file_var.set(
                (
                    "Batch processing "
                    "was cancelled."
                )
            )

            self._append_log(
                (
                    "BATCH   | "
                    "Processing cancelled."
                )
            )

            LOGGER.warning(
                (
                    "Batch cancelled | "
                    "success=%s | "
                    "failed=%s | "
                    "total=%s"
                ),
                summary.success,
                summary.failed,
                summary.total,
            )

            messagebox.showwarning(
                "Processing Cancelled",
                (
                    "Batch processing "
                    "was cancelled."
                ),
            )

            return

        self.progress_var.set(
            100
        )

        self.progress_text_var.set(
            "100%"
        )

        self.status_var.set(
            "Completed"
        )

        self.current_file_var.set(
            (
                "Batch processing "
                "completed."
            )
        )

        self._append_log(
            (
                "BATCH   | "
                f"success="
                f"{summary.success} | "
                f"failed="
                f"{summary.failed} | "
                f"total="
                f"{summary.total}"
            )
        )

        LOGGER.info(
            (
                "Batch completed | "
                "success=%s | "
                "failed=%s | "
                "total=%s"
            ),
            summary.success,
            summary.failed,
            summary.total,
        )

        if summary.failed == 0:

            messagebox.showinfo(
                "Completed",
                (
                    "All documents were "
                    "processed successfully.\n\n"
                    f"Success: "
                    f"{summary.success}\n"
                    f"Failed: "
                    f"{summary.failed}\n"
                    f"Total: "
                    f"{summary.total}"
                ),
            )

            return

        self._show_failure_dialog(
            summary
        )

    # ========================================================
    # Failure Dialog
    # ========================================================

    def _show_failure_dialog(
        self,
        summary: BatchSummary,
    ) -> None:

        lines = [
            (
                "Batch completed "
                "with errors."
            ),
            "",
            (
                f"Success: "
                f"{summary.success}"
            ),
            (
                f"Failed: "
                f"{summary.failed}"
            ),
            (
                f"Total: "
                f"{summary.total}"
            ),
            "",
            "Failed documents:",
        ]

        for index, failure in enumerate(
            self.failures[:5],
            start=1,
        ):

            lines.extend(
                [
                    "",
                    (
                        f"{index}. "
                        f"{failure.file_path.name}"
                    ),
                    (
                        f"   "
                        f"{failure.error_type}: "
                        f"{failure.error_message}"
                    ),
                ]
            )

        if len(
            self.failures
        ) > 5:

            lines.extend(
                [
                    "",
                    (
                        "... additional failures "
                        "are available in "
                        "logs/gui.log"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                (
                    "Full exception details:"
                ),
                str(
                    LOG_DIR
                    / "gui.log"
                ),
            ]
        )

        messagebox.showwarning(
            "Completed with Errors",
            "\n".join(
                lines
            ),
        )

    # ========================================================
    # Controls
    # ========================================================

    def _set_controls_enabled(
        self,
        enabled: bool,
    ) -> None:

        state = (
            NORMAL
            if enabled
            else DISABLED
        )

        widgets = (
            self.add_files_button,
            self.remove_files_button,
            self.clear_files_button,
            self.output_button,
            self.output_entry,
            self.json_checkbox,
            self.database_checkbox,
            self.convert_button,
            self.add_json_files_button,
            self.remove_json_files_button,
            self.clear_json_files_button,
            self.import_json_button,
            self.postgres_test_button,
            self.postgres_save_button,
            self.postgres_defaults_button,
            self.postgres_clear_password_button,
            self.postgres_remember_checkbox,
            *self.postgres_setting_entries,
        )

        for widget in widgets:

            widget.configure(
                state=state
            )

        if hasattr(
            self,
            "postgres_create_tables_button",
        ):
            self.postgres_create_tables_button.configure(
                state=(
                    NORMAL
                    if (
                        enabled
                        and self.postgres_connection_verified
                    )
                    else DISABLED
                )
            )

    # ========================================================
    # GUI Log
    # ========================================================

    def _append_log(
        self,
        message: str,
    ) -> None:

        self.log_text.configure(
            state=NORMAL
        )

        self.log_text.insert(
            END,
            (
                message
                + "\n"
            ),
        )

        self.log_text.see(
            END
        )

        self.log_text.configure(
            state=DISABLED
        )

    def _clear_log(
        self,
    ) -> None:

        self.log_text.configure(
            state=NORMAL
        )

        self.log_text.delete(
            "1.0",
            END,
        )

        self.log_text.configure(
            state=DISABLED
        )

    # ========================================================
    # Close
    # ========================================================

    def _on_close(
        self,
    ) -> None:

        if self.is_processing:

            confirmed = (
                messagebox.askyesno(
                    "Exit Application",
                    (
                        "Document processing "
                        "is still running.\n\n"
                        "Exit anyway?"
                    ),
                )
            )

            if not confirmed:
                return

            self.cancel_requested.set()

        LOGGER.info(
            "GUI application closed."
        )

        self.root.destroy()


# ============================================================
# Application Entry
# ============================================================


def main() -> None:

    root = ttk.Window(
        themename="flatly"
    )

    DocumentIngestionGUI(
        root
    )

    root.mainloop()


if __name__ == "__main__":
    main()