from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from app.pipeline.pipeline_factory import PipelineFactory


LOGGER = logging.getLogger(
    "document_ingestion"
)


# =====================
# Runtime Environment
# =====================

IS_FROZEN = bool(
    getattr(
        sys,
        "frozen",
        False,
    )
)

SAVE_JSON = True

# Python 开发环境：
#     写入 PostgreSQL
#
# PyInstaller EXE：
#     不连接 PostgreSQL
SAVE_DATABASE = not IS_FROZEN


def get_application_directory() -> Path:
    """
    获取应用程序运行目录。

    开发环境：
        返回项目根目录。

    PyInstaller 环境：
        返回 EXE 所在目录。
    """

    if IS_FROZEN:
        return Path(
            sys.executable
        ).resolve().parent

    return Path(
        __file__
    ).resolve().parents[1]


BASE_DIR = get_application_directory()

INPUT_DIR = (
    BASE_DIR
    / "input"
)

OUTPUT_DIR = (
    BASE_DIR
    / "output"
)

LOG_DIR = (
    BASE_DIR
    / "logs"
)


def configure_logging() -> None:
    """
    初始化控制台和文件日志。
    """

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = (
        LOG_DIR
        / "application.log"
    )

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_file,
                encoding="utf-8",
            ),
            logging.StreamHandler(
                sys.stdout
            ),
        ],
        force=True,
    )


def ensure_directories() -> None:
    """
    创建运行所需目录。
    """

    for directory in (
        INPUT_DIR,
        OUTPUT_DIR,
        LOG_DIR,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def discover_input_files() -> list[Path]:
    """
    获取 input 目录下所有受支持的文档。

    排序规则：
        1. 扩展名
        2. 文件名

    忽略：
        - Office 临时文件
        - 不受支持的扩展名
        - 目录
    """

    return sorted(
        (
            file
            for file in INPUT_DIR.iterdir()
            if (
                file.is_file()
                and not file.name.startswith(
                    "~$"
                )
                and PipelineFactory.supports(
                    file
                )
            )
        ),
        key=lambda file: (
            file.suffix.lower(),
            file.name.lower(),
        ),
    )


def process_file(
    file_path: Path,
) -> bool:
    """
    处理单个文件。

    Args:
        file_path:
            输入文件路径。

    Returns:
        True:
            处理成功。

        False:
            处理失败。
    """

    output_path = (
        OUTPUT_DIR
        / f"{file_path.stem}.json"
    )

    print()
    print("====================")
    print(
        f"Processing: {file_path.name}"
    )
    print("====================")

    LOGGER.info(
        "Processing started: %s",
        file_path,
    )

    try:
        pipeline = PipelineFactory.create(
            file_path,
            save_json=SAVE_JSON,
            save_database=SAVE_DATABASE,
        )

        pipeline_name = (
            pipeline.__class__.__name__
        )

        print(
            "Pipeline:",
            pipeline_name,
        )

        print(
            "JSON:",
            (
                "Enabled"
                if SAVE_JSON
                else "Disabled"
            ),
        )

        print(
            "PostgreSQL:",
            (
                "Enabled"
                if SAVE_DATABASE
                else "Disabled"
            ),
        )

        LOGGER.info(
            "Selected pipeline: %s",
            pipeline_name,
        )

        LOGGER.info(
            (
                "Pipeline options | "
                "save_json=%s | "
                "save_database=%s"
            ),
            SAVE_JSON,
            SAVE_DATABASE,
        )

        document = pipeline.run(
            file_path=file_path,
            output=output_path,
        )

        print("Completed")
        print(
            "Pages:",
            len(document.pages),
        )
        print(
            "Chapters:",
            len(document.chapters),
        )
        print(
            "Sections:",
            len(document.sections),
        )
        print(
            "Contents:",
            len(document.contents),
        )

        if SAVE_JSON:
            print(
                "Output:",
                output_path,
            )

        if SAVE_DATABASE:
            print(
                "Database:",
                "Saved",
            )

        LOGGER.info(
            (
                "Processing completed | "
                "file=%s | "
                "pipeline=%s | "
                "pages=%s | "
                "chapters=%s | "
                "sections=%s | "
                "contents=%s | "
                "save_json=%s | "
                "save_database=%s | "
                "output=%s"
            ),
            file_path.name,
            pipeline_name,
            len(document.pages),
            len(document.chapters),
            len(document.sections),
            len(document.contents),
            SAVE_JSON,
            SAVE_DATABASE,
            output_path,
        )

        return True

    except Exception as exc:
        print(
            f"Failed: {file_path.name}"
        )

        print(exc)

        LOGGER.error(
            (
                "Processing failed | "
                "file=%s | "
                "save_json=%s | "
                "save_database=%s | "
                "error=%s"
            ),
            file_path.name,
            SAVE_JSON,
            SAVE_DATABASE,
            exc,
        )

        LOGGER.error(
            traceback.format_exc()
        )

        return False


def print_runtime_information() -> None:
    """
    输出当前运行模式和目录信息。
    """

    runtime_mode = (
        "PyInstaller EXE"
        if IS_FROZEN
        else "Python"
    )

    database_status = (
        "Enabled"
        if SAVE_DATABASE
        else "Disabled"
    )

    print()
    print("========================================")
    print("Document Ingestion Platform")
    print("========================================")
    print(
        "Runtime:",
        runtime_mode,
    )
    print(
        "Base directory:",
        BASE_DIR,
    )
    print(
        "Input directory:",
        INPUT_DIR,
    )
    print(
        "Output directory:",
        OUTPUT_DIR,
    )
    print(
        "Log directory:",
        LOG_DIR,
    )
    print(
        "PostgreSQL:",
        database_status,
    )
    print(
        "Supported formats:",
        ", ".join(
            PipelineFactory.supported_extensions()
        ),
    )
    print("========================================")


def print_batch_summary(
    *,
    success_count: int,
    failure_count: int,
    total_count: int,
) -> None:
    """
    输出批处理汇总。
    """

    print()
    print("====================")
    print("Batch Summary")
    print("====================")
    print(
        "Success:",
        success_count,
    )
    print(
        "Failed:",
        failure_count,
    )
    print(
        "Total:",
        total_count,
    )
    print(
        "PostgreSQL:",
        (
            "Enabled"
            if SAVE_DATABASE
            else "Disabled"
        ),
    )


def wait_before_exit() -> None:
    """
    双击 EXE 运行时暂停窗口。

    普通 Python 开发环境中不暂停。
    """

    if not IS_FROZEN:
        return

    try:
        input(
            "\nPress Enter to exit..."
        )

    except (
        EOFError,
        KeyboardInterrupt,
    ):
        pass


def main() -> None:
    """
    批量处理 input 目录中的所有受支持文档。

    开发环境：
        python -m app.main

        - 保存 JSON
        - 保存 PostgreSQL

    EXE 环境：
        DocumentIngestion.exe

        - 保存 JSON
        - 不连接 PostgreSQL
    """

    ensure_directories()
    configure_logging()
    print_runtime_information()

    LOGGER.info(
        "Application started."
    )

    LOGGER.info(
        "Runtime mode: %s",
        (
            "frozen"
            if IS_FROZEN
            else "python"
        ),
    )

    LOGGER.info(
        "Base directory: %s",
        BASE_DIR,
    )

    LOGGER.info(
        "Input directory: %s",
        INPUT_DIR,
    )

    LOGGER.info(
        "Output directory: %s",
        OUTPUT_DIR,
    )

    LOGGER.info(
        "Log directory: %s",
        LOG_DIR,
    )

    LOGGER.info(
        "JSON output enabled: %s",
        SAVE_JSON,
    )

    LOGGER.info(
        "PostgreSQL storage enabled: %s",
        SAVE_DATABASE,
    )

    files = discover_input_files()

    if not files:
        message = (
            "No supported input files found. "
            f"Input directory: {INPUT_DIR}"
        )

        print()
        print(message)

        LOGGER.warning(
            message
        )

        wait_before_exit()
        return

    LOGGER.info(
        "Discovered %s supported input files.",
        len(files),
    )

    for file_path in files:
        LOGGER.info(
            "Discovered input file: %s",
            file_path.name,
        )

    success_count = 0
    failure_count = 0

    for file_path in files:
        success = process_file(
            file_path
        )

        if success:
            success_count += 1

        else:
            failure_count += 1

    print_batch_summary(
        success_count=success_count,
        failure_count=failure_count,
        total_count=len(files),
    )

    LOGGER.info(
        (
            "Batch completed | "
            "success=%s | "
            "failed=%s | "
            "total=%s | "
            "save_json=%s | "
            "save_database=%s"
        ),
        success_count,
        failure_count,
        len(files),
        SAVE_JSON,
        SAVE_DATABASE,
    )

    wait_before_exit()


if __name__ == "__main__":
    main()