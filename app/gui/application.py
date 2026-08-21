from __future__ import annotations

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
from tkinter import filedialog, messagebox, ttk
from typing import Any

from app.pipeline.pipeline_factory import PipelineFactory


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

        self.is_processing = False

        self.cancel_requested = (
            threading.Event()
        )

        self._configure_window()

        self._create_variables()

        self._build_ui()

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
            "1100x820"
        )

        self.root.minsize(
            900,
            700,
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
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

    # ========================================================
    # Main UI
    # ========================================================

    def _build_ui(
        self,
    ) -> None:

        container = ttk.Frame(
            self.root,
            padding=20,
        )

        container.pack(
            fill=BOTH,
            expand=True,
        )

        self._build_header(
            container
        )

        self._build_input_section(
            container
        )

        self._build_output_section(
            container
        )

        self._build_options_section(
            container
        )

        self._build_action_section(
            container
        )

        self._build_progress_section(
            container
        )

        self._build_log_section(
            container
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
                16,
            ),
        )

        ttk.Label(
            frame,
            text=APP_NAME,
            font=(
                "Segoe UI",
                20,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        ttk.Label(
            frame,
            text=(
                "Document ingestion for "
                "PDF / DOCX / PPTX / XLSX"
            ),
        ).pack(
            anchor="w",
            pady=(
                4,
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
            text="Input Files",
            padding=12,
        )

        frame.pack(
            fill=BOTH,
            pady=(
                0,
                12,
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
                height=8,
                selectmode=EXTENDED,
                activestyle="none",
            )
        )

        scrollbar = ttk.Scrollbar(
            list_container,
            orient=VERTICAL,
            command=(
                self.file_listbox
                .yview
            ),
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

        button_frame = ttk.Frame(
            frame
        )

        button_frame.pack(
            fill=X,
            pady=(
                10,
                0,
            ),
        )

        self.add_files_button = (
            ttk.Button(
                button_frame,
                text="Add Files",
                command=(
                    self.select_files
                ),
            )
        )

        self.add_files_button.pack(
            side=LEFT
        )

        self.remove_files_button = (
            ttk.Button(
                button_frame,
                text="Remove Selected",
                command=(
                    self.remove_selected_files
                ),
            )
        )

        self.remove_files_button.pack(
            side=LEFT,
            padx=(
                10,
                0,
            ),
        )

        self.clear_files_button = (
            ttk.Button(
                button_frame,
                text="Clear",
                command=(
                    self.clear_files
                ),
            )
        )

        self.clear_files_button.pack(
            side=LEFT,
            padx=(
                10,
                0,
            ),
        )

        ttk.Label(
            button_frame,
            textvariable=(
                self.file_count_var
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
            text="Output Directory",
            padding=12,
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        self.output_entry = (
            ttk.Entry(
                frame,
                textvariable=(
                    self.output_directory_var
                ),
            )
        )

        self.output_entry.pack(
            side=LEFT,
            fill=X,
            expand=True,
            padx=(
                0,
                10,
            ),
        )

        self.output_button = (
            ttk.Button(
                frame,
                text="Select Folder",
                command=(
                    self.select_output_directory
                ),
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
            text="Processing Options",
            padding=12,
        )

        frame.pack(
            fill=X,
            pady=(
                0,
                12,
            ),
        )

        self.json_checkbox = (
            ttk.Checkbutton(
                frame,
                text="Generate JSON",
                variable=(
                    self.save_json_var
                ),
            )
        )

        self.json_checkbox.pack(
            side=LEFT,
            padx=(
                0,
                25,
            ),
        )

        self.database_checkbox = (
            ttk.Checkbutton(
                frame,
                text="Save to PostgreSQL",
                variable=(
                    self.save_database_var
                ),
            )
        )

        self.database_checkbox.pack(
            side=LEFT
        )

    # ========================================================
    # Actions
    # ========================================================

    def _build_action_section(
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
                12,
            ),
        )

        self.cancel_button = (
            ttk.Button(
                frame,
                text="Cancel",
                command=(
                    self.cancel_processing
                ),
                state=DISABLED,
            )
        )

        self.cancel_button.pack(
            side=RIGHT,
            padx=(
                10,
                0,
            ),
            ipadx=20,
            ipady=7,
        )

        self.convert_button = (
            ttk.Button(
                frame,
                text="Convert",
                command=(
                    self.start_processing
                ),
            )
        )

        self.convert_button.pack(
            side=RIGHT,
            ipadx=30,
            ipady=7,
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
            text="Progress",
            padding=12,
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
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side=LEFT
        )

        ttk.Label(
            header,
            textvariable=(
                self.progress_text_var
            ),
        ).pack(
            side=RIGHT
        )

        ttk.Label(
            frame,
            textvariable=(
                self.current_file_var
            ),
        ).pack(
            anchor="w",
            pady=(
                6,
                8,
            ),
        )

        self.progress_bar = (
            ttk.Progressbar(
                frame,
                variable=(
                    self.progress_var
                ),
                maximum=100,
            )
        )

        self.progress_bar.pack(
            fill=X
        )

        ttk.Label(
            frame,
            textvariable=(
                self.summary_var
            ),
        ).pack(
            anchor="w",
            pady=(
                8,
                0,
            ),
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
            padding=12,
        )

        frame.pack(
            fill=BOTH,
            expand=True,
        )

        self.log_text = tk.Text(
            frame,
            state=DISABLED,
            wrap=WORD,
            height=12,
            font=(
                "Consolas",
                9,
            ),
        )

        scrollbar = ttk.Scrollbar(
            frame,
            orient=VERTICAL,
            command=(
                self.log_text
                .yview
            ),
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
    # Input Files
    # ========================================================

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
        )

        for widget in widgets:

            widget.configure(
                state=state
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

    root = tk.Tk()

    DocumentIngestionGUI(
        root
    )

    root.mainloop()


if __name__ == "__main__":
    main()