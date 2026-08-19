from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from app.config.config_loader import (
    AppConfig,
    ConfigLoader,
    ConfigurationError,
)

from app.pipeline.pipeline_factory import (
    PipelineFactory,
)


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


def get_application_directory() -> Path:
    """
    获取应用程序运行目录。

    Python 开发环境：
        返回项目根目录。

    PyInstaller EXE：
        返回 EXE 所在目录。
    """

    if IS_FROZEN:
        return Path(
            sys.executable
        ).resolve().parent

    return Path(
        __file__
    ).resolve().parents[1]


BASE_DIR = (
    get_application_directory()
)


def load_application_config() -> AppConfig:
    """
    加载应用配置。

    默认位置：

        Python:
            <project>/config/config.yaml

        EXE:
            <exe>/config/config.yaml

    Returns:
        AppConfig

    Raises:
        ConfigurationError:
            配置文件不存在、格式错误或校验失败。
    """

    try:
        return ConfigLoader.load()

    except ConfigurationError:
        raise

    except Exception as exc:
        raise ConfigurationError(
            "Unexpected configuration loading error: "
            f"{exc}"
        ) from exc


CONFIG = load_application_config()


# =====================
# Runtime Paths
# =====================

INPUT_DIR = (
    BASE_DIR
    / CONFIG.runtime.input_directory
).resolve()

OUTPUT_DIR = (
    BASE_DIR
    / CONFIG.runtime.output_directory
).resolve()

LOG_DIR = (
    BASE_DIR
    / CONFIG.runtime.log_directory
).resolve()


# =====================
# Runtime Options
# =====================

SAVE_JSON = (
    CONFIG.output.save_json
)

SAVE_DATABASE = (
    CONFIG.database.enabled
)

CHUNK_MAX_LENGTH = (
    CONFIG.chunk.max_length
)


def configure_logging() -> None:
    """
    初始化日志系统。

    日志配置从 config.yaml 获取：

        logging.level
        logging.file_name
    """

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = (
        LOG_DIR
        / CONFIG.logging.file_name
    )

    log_level = getattr(
        logging,
        CONFIG.logging.level,
        logging.INFO,
    )

    logging.basicConfig(
        level=log_level,
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

    不依赖目录预先存在。
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
    获取 input 目录下所有受支持文档。

    排序规则：
        1. 扩展名
        2. 文件名

    自动忽略：
        - Office 临时文件
        - 未支持格式
        - 文件夹
    """

    files = [
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
    ]

    return sorted(
        files,
        key=lambda file: (
            file.suffix.lower(),
            file.name.lower(),
        ),
    )


def build_pipeline_kwargs() -> dict:
    """
    构建统一 Pipeline 初始化参数。

    当前所有 Pipeline 共用：

        save_json
        save_database
        chunk_max_length
    """

    return {
        "save_json": SAVE_JSON,
        "save_database": SAVE_DATABASE,
        "chunk_max_length": CHUNK_MAX_LENGTH,
    }


def process_file(
    file_path: Path,
) -> bool:
    """
    处理单个文档。

    Args:
        file_path:
            输入文档路径。

    Returns:
        True:
            成功。

        False:
            失败。
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
        "Processing started | file=%s",
        file_path,
    )

    try:
        pipeline = (
            PipelineFactory.create(
                file_path,
                **build_pipeline_kwargs(),
            )
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

        print(
            "Chunk max length:",
            CHUNK_MAX_LENGTH,
        )

        LOGGER.info(
            "Pipeline selected | "
            "file=%s | "
            "pipeline=%s | "
            "save_json=%s | "
            "save_database=%s | "
            "chunk_max_length=%s",
            file_path.name,
            pipeline_name,
            SAVE_JSON,
            SAVE_DATABASE,
            CHUNK_MAX_LENGTH,
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
            "Processing completed | "
            "file=%s | "
            "pipeline=%s | "
            "pages=%s | "
            "chapters=%s | "
            "sections=%s | "
            "contents=%s | "
            "save_json=%s | "
            "save_database=%s | "
            "output=%s",
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
            "Processing failed | "
            "file=%s | "
            "error=%s",
            file_path.name,
            exc,
        )

        LOGGER.debug(
            traceback.format_exc()
        )

        return False


def print_runtime_information() -> None:
    """
    输出当前运行环境与应用配置。

    注意：
        不打印数据库密码。
    """

    runtime_mode = (
        "PyInstaller EXE"
        if IS_FROZEN
        else "Python"
    )

    print()
    print(
        "========================================"
    )
    print(
        CONFIG.application.name
    )
    print(
        "========================================"
    )

    print(
        "Runtime:",
        runtime_mode,
    )

    print(
        "Environment:",
        CONFIG.application.environment,
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

    if SAVE_DATABASE:
        print(
            "DB Host:",
            CONFIG.database.host,
        )

        print(
            "DB Port:",
            CONFIG.database.port,
        )

        print(
            "DB Name:",
            CONFIG.database.database,
        )

        print(
            "DB User:",
            CONFIG.database.user,
        )

    print(
        "Chunk max length:",
        CHUNK_MAX_LENGTH,
    )

    print(
        "Supported formats:",
        ", ".join(
            PipelineFactory
            .supported_extensions()
        ),
    )

    print(
        "========================================"
    )


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


def wait_before_exit() -> None:
    """
    EXE 环境下暂停窗口。

    Python 开发环境不暂停。
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
    Document Ingestion Platform 主入口。

    流程：

        Config
            ↓

        Runtime Directories
            ↓

        Input Discovery
            ↓

        PipelineFactory
            ↓

        PDF / DOCX / PPTX / XLSX Pipeline
            ↓

        JSON
            +
        PostgreSQL
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
        "Environment: %s",
        CONFIG.application.environment,
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
        "JSON enabled: %s",
        SAVE_JSON,
    )

    LOGGER.info(
        "PostgreSQL enabled: %s",
        SAVE_DATABASE,
    )

    LOGGER.info(
        "Chunk max length: %s",
        CHUNK_MAX_LENGTH,
    )

    files = (
        discover_input_files()
    )

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
        "Discovered %s supported files.",
        len(files),
    )

    for file_path in files:
        LOGGER.debug(
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
        "Batch completed | "
        "success=%s | "
        "failed=%s | "
        "total=%s",
        success_count,
        failure_count,
        len(files),
    )

    wait_before_exit()


if __name__ == "__main__":
    try:
        main()

    except ConfigurationError as exc:
        print()
        print(
            "Configuration Error:"
        )
        print(exc)

        if IS_FROZEN:
            try:
                input(
                    "\nPress Enter to exit..."
                )

            except (
                EOFError,
                KeyboardInterrupt,
            ):
                pass

        raise SystemExit(
            2
        ) from exc

    except KeyboardInterrupt:
        print()
        print(
            "Operation cancelled by user."
        )

        raise SystemExit(
            130
        )