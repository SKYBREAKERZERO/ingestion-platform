from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from threading import RLock
from typing import Any

from app.router.format_router import (
    FormatRoute,
    FormatRouter,
    UnsupportedFormatError,
)


class PipelineFactoryError(RuntimeError):
    """Pipeline 工厂基础异常。"""


class UnsupportedFileTypeError(PipelineFactoryError):
    """输入文件格式不受支持。"""


class PipelineLoadError(PipelineFactoryError):
    """Pipeline 模块或类加载失败。"""


@dataclass(frozen=True)
class PipelineSpec:
    """
    Pipeline 延迟加载配置。

    attributes:
        module_path:
            Python 模块路径。

        class_name:
            Pipeline 类名。
    """

    module_path: str

    class_name: str


class PipelineFactory:
    """
    Pipeline 实例工厂。

    职责：
        - 通过 FormatRouter 获取 pipeline_key
        - 根据 pipeline_key 查找 PipelineSpec
        - 延迟导入 Pipeline 类
        - 实例化对应 Pipeline

    不负责：
        - 文件格式识别规则
        - 执行 Pipeline
        - 输出路径管理
        - 批量处理
    """

    _lock = RLock()

    _registry: dict[str, PipelineSpec] = {
        "pdf": PipelineSpec(
            module_path="app.pipeline.pdf_pipeline",
            class_name="PDFPipeline",
        ),
        "docx": PipelineSpec(
            module_path="app.pipeline.docx_pipeline",
            class_name="DOCXPipeline",
        ),
        "xlsx": PipelineSpec(
            module_path="app.pipeline.xlsx_pipeline",
            class_name="XLSXPipeline",
        ),
        "pptx": PipelineSpec(
            module_path="app.pipeline.pptx_pipeline",
            class_name="PPTXPipeline",
        ),
        "txt": PipelineSpec(
            module_path="app.pipeline.txt_pipeline",
            class_name="TXTPipeline",
        ),
    }

    @classmethod
    def create(
        cls,
        file_path: str | Path,
        **pipeline_kwargs: Any,
    ) -> Any:
        """
        根据文件路径创建对应 Pipeline。

        Args:
            file_path:
                输入文件路径。

            **pipeline_kwargs:
                传递给 Pipeline 构造函数的参数。

        Returns:
            Pipeline 实例。
        """

        path = cls._validate_file_path(
            file_path
        )

        try:
            format_route = FormatRouter.route(
                path
            )

        except UnsupportedFormatError as exc:
            raise UnsupportedFileTypeError(
                str(exc)
            ) from exc

        return cls.create_by_route(
            format_route=format_route,
            file_path=path,
            **pipeline_kwargs,
        )

    @classmethod
    def create_by_route(
        cls,
        *,
        format_route: FormatRoute,
        file_path: str | Path | None = None,
        **pipeline_kwargs: Any,
    ) -> Any:
        """
        根据 FormatRoute 创建 Pipeline。

        PipelineRouter 已经完成格式识别时，
        可以直接使用该方法，避免重复 route。
        """

        pipeline_key = cls._normalize_pipeline_key(
            format_route.pipeline_key
        )

        spec = cls._registry.get(
            pipeline_key
        )

        if spec is None:
            supported = ", ".join(
                cls.supported_pipeline_keys()
            )

            raise UnsupportedFileTypeError(
                f"No pipeline registered for key: "
                f"{pipeline_key}. "
                f"Supported pipeline keys: {supported}"
            )

        pipeline_class = cls._load_pipeline_class(
            pipeline_key=pipeline_key,
            spec=spec,
        )

        try:
            return pipeline_class(
                **pipeline_kwargs
            )

        except Exception as exc:
            file_name = (
                Path(file_path).name
                if file_path is not None
                else "<unknown>"
            )

            raise PipelineLoadError(
                f"Failed to initialize pipeline "
                f"'{spec.class_name}' for "
                f"'{file_name}': {exc}"
            ) from exc

    @classmethod
    def supports(
        cls,
        file_path_or_extension: str | Path,
    ) -> bool:
        """
        判断文件格式是否存在可用 Pipeline。

        同时要求：
            1. FormatRouter 支持该格式
            2. 对应 pipeline_key 已注册
        """

        if not FormatRouter.supports(
            file_path_or_extension
        ):
            return False

        try:
            route = FormatRouter.route(
                file_path_or_extension,
                validate_exists=False,
            )

        except Exception:
            return False

        pipeline_key = cls._normalize_pipeline_key(
            route.pipeline_key
        )

        return pipeline_key in cls._registry

    @classmethod
    def supported_pipeline_keys(
        cls,
    ) -> tuple[str, ...]:
        """返回已经注册的 Pipeline Key。"""

        return tuple(
            sorted(
                cls._registry.keys()
            )
        )

    @classmethod
    def supported_extensions(
        cls,
    ) -> tuple[str, ...]:
        """
        返回同时被 FormatRouter 和 PipelineFactory 支持的扩展名。
        """

        supported: list[str] = []

        for extension in (
            FormatRouter.supported_extensions()
        ):
            try:
                route = FormatRouter.route(
                    extension,
                    validate_exists=False,
                )

            except Exception:
                continue

            pipeline_key = (
                cls._normalize_pipeline_key(
                    route.pipeline_key
                )
            )

            if pipeline_key in cls._registry:
                supported.append(
                    extension
                )

        return tuple(
            sorted(
                supported
            )
        )

    @classmethod
    def register(
        cls,
        pipeline_key: str,
        module_path: str,
        class_name: str,
        *,
        overwrite: bool = False,
    ) -> None:
        """
        动态注册 Pipeline。

        Example:
            PipelineFactory.register(
                pipeline_key="markdown",
                module_path=(
                    "app.pipeline.markdown_pipeline"
                ),
                class_name="MarkdownPipeline",
            )
        """

        normalized_key = (
            cls._normalize_pipeline_key(
                pipeline_key
            )
        )

        if not normalized_key:
            raise ValueError(
                "pipeline_key cannot be empty."
            )

        if not module_path.strip():
            raise ValueError(
                "module_path cannot be empty."
            )

        if not class_name.strip():
            raise ValueError(
                "class_name cannot be empty."
            )

        with cls._lock:
            if (
                normalized_key in cls._registry
                and not overwrite
            ):
                raise ValueError(
                    f"Pipeline already registered for: "
                    f"{normalized_key}"
                )

            cls._registry[
                normalized_key
            ] = PipelineSpec(
                module_path=module_path.strip(),
                class_name=class_name.strip(),
            )

    @classmethod
    def unregister(
        cls,
        pipeline_key: str,
    ) -> None:
        """删除 Pipeline 注册。"""

        normalized_key = (
            cls._normalize_pipeline_key(
                pipeline_key
            )
        )

        with cls._lock:
            cls._registry.pop(
                normalized_key,
                None,
            )

    @classmethod
    def _load_pipeline_class(
        cls,
        *,
        pipeline_key: str,
        spec: PipelineSpec,
    ) -> type:
        """延迟导入并返回 Pipeline 类。"""

        try:
            module = import_module(
                spec.module_path
            )

        except Exception as exc:
            raise PipelineLoadError(
                f"Failed to import pipeline module "
                f"'{spec.module_path}' for "
                f"pipeline key '{pipeline_key}': {exc}"
            ) from exc

        try:
            pipeline_class = getattr(
                module,
                spec.class_name,
            )

        except AttributeError as exc:
            raise PipelineLoadError(
                f"Pipeline class "
                f"'{spec.class_name}' was not found "
                f"in module '{spec.module_path}'."
            ) from exc

        if not isinstance(
            pipeline_class,
            type,
        ):
            raise PipelineLoadError(
                f"Registered pipeline "
                f"'{spec.module_path}."
                f"{spec.class_name}' is not a class."
            )

        run_method = getattr(
            pipeline_class,
            "run",
            None,
        )

        if not callable(
            run_method
        ):
            raise PipelineLoadError(
                f"Pipeline class "
                f"'{spec.class_name}' must implement "
                f"a callable run() method."
            )

        return pipeline_class

    @staticmethod
    def _validate_file_path(
        file_path: str | Path,
    ) -> Path:
        """验证输入文件路径。"""

        path = Path(
            file_path
        ).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"Input file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        return path

    @staticmethod
    def _normalize_pipeline_key(
        pipeline_key: str,
    ) -> str:
        """规范化 Pipeline 注册键。"""

        return str(
            pipeline_key
        ).strip().lower()