from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """应用配置基础异常。"""


class ConfigurationFileNotFoundError(
    ConfigurationError
):
    """配置文件不存在。"""


class ConfigurationValidationError(
    ConfigurationError
):
    """配置内容校验失败。"""


@dataclass(frozen=True)
class ApplicationConfig:
    """应用基础配置。"""

    name: str
    environment: str


@dataclass(frozen=True)
class RuntimeConfig:
    """运行目录配置。"""

    input_directory: str
    output_directory: str
    log_directory: str


@dataclass(frozen=True)
class OutputConfig:
    """输出配置。"""

    save_json: bool


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL 配置。"""

    enabled: bool
    host: str
    port: int
    database: str
    user: str
    password: str | None
    password_env: str
    connect_timeout: int


@dataclass(frozen=True)
class ChunkConfig:
    """Chunk 配置。"""

    max_length: int


@dataclass(frozen=True)
class LoggingConfig:
    """日志配置。"""

    level: str
    file_name: str


@dataclass(frozen=True)
class AppConfig:
    """
    应用完整配置。
    """

    application: ApplicationConfig
    runtime: RuntimeConfig
    output: OutputConfig
    database: DatabaseConfig
    chunk: ChunkConfig
    logging: LoggingConfig


class ConfigLoader:
    """
    YAML 配置加载器。

    职责：
        1. 定位 config.yaml
        2. 加载 YAML
        3. 校验配置
        4. 读取数据库密码环境变量
        5. 返回强类型 AppConfig

    支持：
        开发环境
        PyInstaller EXE
    """

    DEFAULT_CONFIG_RELATIVE_PATH = (
        Path("config")
        / "config.yaml"
    )

    VALID_LOG_LEVELS = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
    ) -> AppConfig:
        """
        加载应用配置。

        Args:
            config_path:
                可选的自定义 YAML 路径。

        Returns:
            AppConfig
        """

        path = cls.resolve_config_path(
            config_path
        )

        raw_config = cls._load_yaml(
            path
        )

        return cls._build_config(
            raw_config
        )

    @classmethod
    def resolve_config_path(
        cls,
        config_path: str | Path | None = None,
    ) -> Path:
        """
        获取配置文件路径。

        优先级：
            1. 显式 config_path
            2. CONFIG_FILE 环境变量
            3. 应用目录/config/config.yaml
        """

        if config_path is not None:
            path = Path(
                config_path
            ).expanduser()

            return cls._validate_config_path(
                path
            )

        environment_path = os.getenv(
            "CONFIG_FILE"
        )

        if environment_path:
            path = Path(
                environment_path
            ).expanduser()

            return cls._validate_config_path(
                path
            )

        base_directory = (
            cls.get_application_directory()
        )

        path = (
            base_directory
            / cls.DEFAULT_CONFIG_RELATIVE_PATH
        )

        return cls._validate_config_path(
            path
        )

    @staticmethod
    def get_application_directory() -> Path:
        """
        获取程序运行目录。

        开发环境：
            项目根目录

        PyInstaller：
            EXE 所在目录
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

    @staticmethod
    def _validate_config_path(
        path: Path,
    ) -> Path:
        """
        校验配置文件路径。
        """

        resolved_path = (
            path.resolve()
        )

        if not resolved_path.exists():
            raise (
                ConfigurationFileNotFoundError(
                    "Configuration file "
                    f"not found: {resolved_path}"
                )
            )

        if not resolved_path.is_file():
            raise ConfigurationValidationError(
                "Configuration path is "
                f"not a file: {resolved_path}"
            )

        if resolved_path.suffix.lower() not in {
            ".yaml",
            ".yml",
        }:
            raise ConfigurationValidationError(
                "Configuration file must "
                "use .yaml or .yml extension. "
                f"Received: "
                f"{resolved_path.suffix}"
            )

        return resolved_path

    @staticmethod
    def _load_yaml(
        path: Path,
    ) -> dict[str, Any]:
        """
        加载 YAML。
        """

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = yaml.safe_load(
                    file
                )

        except yaml.YAMLError as exc:
            raise ConfigurationError(
                "Failed to parse YAML "
                f"configuration: {exc}"
            ) from exc

        except OSError as exc:
            raise ConfigurationError(
                "Failed to read "
                f"configuration file: {exc}"
            ) from exc

        if data is None:
            raise ConfigurationValidationError(
                "Configuration file is empty."
            )

        if not isinstance(
            data,
            dict,
        ):
            raise ConfigurationValidationError(
                "Configuration root "
                "must be a mapping."
            )

        return data

    @classmethod
    def _build_config(
        cls,
        data: dict[str, Any],
    ) -> AppConfig:
        """
        构建强类型配置。
        """

        application_data = (
            cls._get_mapping(
                data,
                "application",
            )
        )

        runtime_data = cls._get_mapping(
            data,
            "runtime",
        )

        output_data = cls._get_mapping(
            data,
            "output",
        )

        database_data = cls._get_mapping(
            data,
            "database",
        )

        chunk_data = cls._get_mapping(
            data,
            "chunk",
        )

        logging_data = cls._get_mapping(
            data,
            "logging",
        )

        application = ApplicationConfig(
            name=cls._get_string(
                application_data,
                "name",
                default=(
                    "Document Ingestion Platform"
                ),
            ),
            environment=cls._get_string(
                application_data,
                "environment",
                default="development",
            ),
        )

        runtime = RuntimeConfig(
            input_directory=cls._get_string(
                runtime_data,
                "input_directory",
                default="input",
            ),
            output_directory=cls._get_string(
                runtime_data,
                "output_directory",
                default="output",
            ),
            log_directory=cls._get_string(
                runtime_data,
                "log_directory",
                default="logs",
            ),
        )

        output = OutputConfig(
            save_json=cls._get_bool(
                output_data,
                "save_json",
                default=True,
            )
        )

        password_env = cls._get_string(
            database_data,
            "password_env",
            default="POSTGRES_PASSWORD",
        )

        password = os.getenv(
            password_env
        )

        database = DatabaseConfig(
            enabled=cls._get_bool(
                database_data,
                "enabled",
                default=False,
            ),
            host=cls._get_string(
                database_data,
                "host",
                default="127.0.0.1",
            ),
            port=cls._get_int(
                database_data,
                "port",
                default=5432,
                minimum=1,
                maximum=65535,
            ),
            database=cls._get_string(
                database_data,
                "database",
                default="rag",
            ),
            user=cls._get_string(
                database_data,
                "user",
                default="postgres",
            ),
            password=password,
            password_env=password_env,
            connect_timeout=cls._get_int(
                database_data,
                "connect_timeout",
                default=10,
                minimum=1,
            ),
        )

        chunk = ChunkConfig(
            max_length=cls._get_int(
                chunk_data,
                "max_length",
                default=1000,
                minimum=1,
            )
        )

        log_level = cls._get_string(
            logging_data,
            "level",
            default="INFO",
        ).upper()

        if log_level not in (
            cls.VALID_LOG_LEVELS
        ):
            raise (
                ConfigurationValidationError(
                    "Invalid logging.level: "
                    f"{log_level}. "
                    "Supported values: "
                    + ", ".join(
                        sorted(
                            cls.VALID_LOG_LEVELS
                        )
                    )
                )
            )

        logging_config = LoggingConfig(
            level=log_level,
            file_name=cls._get_string(
                logging_data,
                "file_name",
                default="application.log",
            ),
        )

        cls._validate_database(
            database
        )

        return AppConfig(
            application=application,
            runtime=runtime,
            output=output,
            database=database,
            chunk=chunk,
            logging=logging_config,
        )

    @staticmethod
    def _validate_database(
        config: DatabaseConfig,
    ) -> None:
        """
        数据库配置最终校验。
        """

        if not config.enabled:
            return

        if not config.host:
            raise (
                ConfigurationValidationError(
                    "database.host "
                    "cannot be empty "
                    "when database is enabled."
                )
            )

        if not config.database:
            raise (
                ConfigurationValidationError(
                    "database.database "
                    "cannot be empty "
                    "when database is enabled."
                )
            )

        if not config.user:
            raise (
                ConfigurationValidationError(
                    "database.user "
                    "cannot be empty "
                    "when database is enabled."
                )
            )

        if not config.password:
            raise (
                ConfigurationValidationError(
                    "PostgreSQL password "
                    "environment variable "
                    f"'{config.password_env}' "
                    "is not configured."
                )
            )

    @staticmethod
    def _get_mapping(
        data: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:

        value = data.get(
            key,
            {}
        )

        if value is None:
            return {}

        if not isinstance(
            value,
            dict,
        ):
            raise ConfigurationValidationError(
                f"Configuration section "
                f"'{key}' must be a mapping."
            )

        return value

    @staticmethod
    def _get_string(
        data: dict[str, Any],
        key: str,
        *,
        default: str,
    ) -> str:

        value = data.get(
            key,
            default,
        )

        if value is None:
            return default

        normalized = str(
            value
        ).strip()

        if not normalized:
            return default

        return normalized

    @staticmethod
    def _get_bool(
        data: dict[str, Any],
        key: str,
        *,
        default: bool,
    ) -> bool:

        value = data.get(
            key,
            default,
        )

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value.strip().lower()
            )

            if normalized in {
                "true",
                "yes",
                "1",
                "on",
            }:
                return True

            if normalized in {
                "false",
                "no",
                "0",
                "off",
            }:
                return False

        raise ConfigurationValidationError(
            f"Configuration value "
            f"'{key}' must be boolean."
        )

    @staticmethod
    def _get_int(
        data: dict[str, Any],
        key: str,
        *,
        default: int,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:

        value = data.get(
            key,
            default,
        )

        try:
            normalized = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise (
                ConfigurationValidationError(
                    f"Configuration value "
                    f"'{key}' must be integer."
                )
            ) from exc

        if (
            minimum is not None
            and normalized < minimum
        ):
            raise ConfigurationValidationError(
                f"Configuration value "
                f"'{key}' must be >= "
                f"{minimum}."
            )

        if (
            maximum is not None
            and normalized > maximum
        ):
            raise ConfigurationValidationError(
                f"Configuration value "
                f"'{key}' must be <= "
                f"{maximum}."
            )

        return normalized