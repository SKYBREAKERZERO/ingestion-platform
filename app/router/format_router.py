from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock


class FormatRouterError(RuntimeError):
    """格式路由基础异常。"""


class UnsupportedFormatError(FormatRouterError):
    """文件格式不受支持。"""


class InvalidInputPathError(FormatRouterError):
    """输入路径无效。"""


@dataclass(frozen=True)
class FormatRoute:
    """
    文件格式路由结果。

    attributes:
        extension:
            标准化扩展名，例如 .pdf

        format_name:
            标准格式名称，例如 pdf

        media_type:
            MIME 类型

        pipeline_key:
            对应 Pipeline 注册键
    """

    extension: str
    format_name: str
    media_type: str
    pipeline_key: str


class FormatRouter:
    """
    文件格式路由器。

    职责：
        - 根据文件扩展名识别格式
        - 返回统一的 FormatRoute
        - 支持动态注册新格式
        - 验证输入路径
        - 提供支持格式查询

    不负责：
        - 创建 Pipeline
        - 加载文件内容
        - 执行文档解析
    """

    _lock = RLock()

    _routes: dict[str, FormatRoute] = {
        ".pdf": FormatRoute(
            extension=".pdf",
            format_name="pdf",
            media_type="application/pdf",
            pipeline_key="pdf",
        ),
        ".docx": FormatRoute(
            extension=".docx",
            format_name="docx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            pipeline_key="docx",
        ),
        ".xlsx": FormatRoute(
            extension=".xlsx",
            format_name="xlsx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            pipeline_key="xlsx",
        ),
        ".xls": FormatRoute(
            extension=".xls",
            format_name="xls",
            media_type="application/vnd.ms-excel",
            pipeline_key="xlsx",
        ),
        ".pptx": FormatRoute(
            extension=".pptx",
            format_name="pptx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            pipeline_key="pptx",
        ),
        ".ppt": FormatRoute(
            extension=".ppt",
            format_name="ppt",
            media_type="application/vnd.ms-powerpoint",
            pipeline_key="pptx",
        ),
        ".txt": FormatRoute(
            extension=".txt",
            format_name="txt",
            media_type="text/plain",
            pipeline_key="txt",
        ),
        ".csv": FormatRoute(
            extension=".csv",
            format_name="csv",
            media_type="text/csv",
            pipeline_key="csv",
        ),
        ".md": FormatRoute(
            extension=".md",
            format_name="markdown",
            media_type="text/markdown",
            pipeline_key="markdown",
        ),
        ".html": FormatRoute(
            extension=".html",
            format_name="html",
            media_type="text/html",
            pipeline_key="html",
        ),
        ".htm": FormatRoute(
            extension=".htm",
            format_name="html",
            media_type="text/html",
            pipeline_key="html",
        ),
        ".xml": FormatRoute(
            extension=".xml",
            format_name="xml",
            media_type="application/xml",
            pipeline_key="xml",
        ),
    }

    @classmethod
    def route(
        cls,
        file_path: str | Path,
        *,
        validate_exists: bool = True,
    ) -> FormatRoute:
        """
        根据文件路径返回格式路由结果。

        Args:
            file_path:
                输入文件路径。

            validate_exists:
                是否检查文件是否真实存在。

        Raises:
            InvalidInputPathError:
                路径为空、不存在或不是文件。

            UnsupportedFormatError:
                扩展名不在注册表中。
        """

        path = cls._normalize_path(
            file_path
        )

        if validate_exists:
            cls._validate_path(
                path
            )

        extension = cls._normalize_extension(
            path.suffix
        )

        route = cls._routes.get(
            extension
        )

        if route is None:
            supported = ", ".join(
                cls.supported_extensions()
            )

            raise UnsupportedFormatError(
                f"Unsupported file format: "
                f"{extension or '<no extension>'}. "
                f"Supported formats: {supported}"
            )

        return route

    @classmethod
    def detect_format(
        cls,
        file_path: str | Path,
        *,
        validate_exists: bool = True,
    ) -> str:
        """
        返回标准格式名。

        Example:
            test.docx -> docx
            report.htm -> html
        """

        return cls.route(
            file_path,
            validate_exists=validate_exists,
        ).format_name

    @classmethod
    def get_pipeline_key(
        cls,
        file_path: str | Path,
        *,
        validate_exists: bool = True,
    ) -> str:
        """
        返回 Pipeline 注册键。
        """

        return cls.route(
            file_path,
            validate_exists=validate_exists,
        ).pipeline_key

    @classmethod
    def supports(
        cls,
        file_path_or_extension: str | Path,
    ) -> bool:
        """
        判断路径或扩展名是否受支持。

        Examples:
            FormatRouter.supports("spec.pdf")
            FormatRouter.supports(".docx")
            FormatRouter.supports("xlsx")
        """

        value = str(
            file_path_or_extension
        ).strip()

        if not value:
            return False

        if (
            "/" not in value
            and "\\" not in value
            and "." not in value
        ):
            extension = cls._normalize_extension(
                value
            )

        elif (
            value.startswith(".")
            and "/" not in value
            and "\\" not in value
        ):
            extension = cls._normalize_extension(
                value
            )

        else:
            extension = cls._normalize_extension(
                Path(value).suffix
            )

        return extension in cls._routes

    @classmethod
    def supported_extensions(
        cls,
    ) -> tuple[str, ...]:
        """返回所有已注册扩展名。"""

        return tuple(
            sorted(
                cls._routes.keys()
            )
        )

    @classmethod
    def supported_formats(
        cls,
    ) -> tuple[str, ...]:
        """返回所有标准格式名。"""

        return tuple(
            sorted(
                {
                    route.format_name
                    for route in cls._routes.values()
                }
            )
        )

    @classmethod
    def register(
        cls,
        *,
        extension: str,
        format_name: str,
        media_type: str,
        pipeline_key: str,
        overwrite: bool = False,
    ) -> None:
        """
        动态注册格式。

        Example:
            FormatRouter.register(
                extension=".json",
                format_name="json",
                media_type="application/json",
                pipeline_key="json",
            )
        """

        normalized_extension = (
            cls._normalize_extension(
                extension
            )
        )

        if not normalized_extension:
            raise ValueError(
                "extension cannot be empty."
            )

        if not format_name.strip():
            raise ValueError(
                "format_name cannot be empty."
            )

        if not media_type.strip():
            raise ValueError(
                "media_type cannot be empty."
            )

        if not pipeline_key.strip():
            raise ValueError(
                "pipeline_key cannot be empty."
            )

        with cls._lock:
            if (
                normalized_extension in cls._routes
                and not overwrite
            ):
                raise ValueError(
                    f"Format already registered: "
                    f"{normalized_extension}"
                )

            cls._routes[
                normalized_extension
            ] = FormatRoute(
                extension=normalized_extension,
                format_name=format_name.strip().lower(),
                media_type=media_type.strip(),
                pipeline_key=pipeline_key.strip().lower(),
            )

    @classmethod
    def unregister(
        cls,
        extension: str,
    ) -> None:
        """取消格式注册。"""

        normalized_extension = (
            cls._normalize_extension(
                extension
            )
        )

        with cls._lock:
            cls._routes.pop(
                normalized_extension,
                None,
            )

    @staticmethod
    def _normalize_path(
        file_path: str | Path,
    ) -> Path:

        value = str(
            file_path
        ).strip()

        if not value:
            raise InvalidInputPathError(
                "Input path cannot be empty."
            )

        return Path(
            value
        ).expanduser()

    @staticmethod
    def _validate_path(
        path: Path,
    ) -> None:

        if not path.exists():
            raise InvalidInputPathError(
                f"Input file not found: {path}"
            )

        if not path.is_file():
            raise InvalidInputPathError(
                f"Input path is not a file: {path}"
            )

    @staticmethod
    def _normalize_extension(
        extension: str,
    ) -> str:

        normalized = str(
            extension
        ).strip().lower()

        if not normalized:
            return ""

        if not normalized.startswith("."):
            normalized = (
                f".{normalized}"
            )

        return normalized