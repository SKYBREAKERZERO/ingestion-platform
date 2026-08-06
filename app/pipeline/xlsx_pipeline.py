from __future__ import annotations

from pathlib import Path

from app.builder.json_builder import JsonBuilder

from app.filter.common.content_filter import ContentFilter
from app.filter.xlsx.row_filter import RowFilter
from app.filter.xlsx.sheet_filter import SheetFilter

from app.loader.xlsx_loader import XLSXLoader

from app.normalizer.unicode_normalizer import UnicodeNormalizer

from app.parser.xlsx_parser import XLSXParser

from app.processor.chunker import Chunker
from app.processor.deduplicator import Deduplicator
from app.processor.section_hierarchy import SectionHierarchyBuilder
from app.processor.sort_order_assigner import SortOrderAssigner
from app.processor.token_counter import TokenCounter

from app.storage.postgres_storage import PostgresStorage


class XLSXPipeline:
    """
    XLSX 文档摄取 Pipeline。

    流程：
        1. 加载 XLSX
        2. Unicode 标准化
        3. 过滤无效 Sheet
        4. 清理无效行
        5. 解析 Sheet、数据区域和正文
        6. 去重
        7. 建立 Section 层级
        8. 分配排序字段
        9. 清理无效正文
        10. Chunk 分块
        11. 统计最终 Chunk Token
        12. 输出 JSON
        13. 保存 PostgreSQL

    默认结构映射：
        Worksheet
            -> Chapter

        连续数据区域
            -> Section

        数据行
            -> Content
    """

    def __init__(
        self,
        *,
        chunk_max_length: int = 1000,
        save_json: bool = True,
        save_database: bool = True,
        loader_read_only: bool = True,
        loader_data_only: bool = True,
        include_hidden_sheets: bool = False,
        include_very_hidden_sheets: bool = False,
        exclude_default_sheet_names: bool = False,
        remove_duplicate_rows: bool = True,
        remove_comment_rows: bool = False,
        remove_summary_rows: bool = False,
        first_row_as_header: bool = True,
        include_header_in_content: bool = True,
        detect_multiple_regions: bool = True,
        maximum_row_gap: int = 1,
    ) -> None:

        if chunk_max_length <= 0:
            raise ValueError(
                "chunk_max_length must be greater than 0."
            )

        if maximum_row_gap < 1:
            raise ValueError(
                "maximum_row_gap must be at least 1."
            )

        self.save_json_enabled = save_json
        self.save_database_enabled = save_database

        # =====================
        # Loader
        # =====================

        self.loader = XLSXLoader(
            read_only=loader_read_only,
            data_only=loader_data_only,
            include_hidden_sheets=(
                include_hidden_sheets
            ),
            include_very_hidden_sheets=(
                include_very_hidden_sheets
            ),
        )

        # =====================
        # Normalizer
        # =====================

        self.unicode_normalizer = (
            UnicodeNormalizer()
        )

        # =====================
        # XLSX Filters
        # =====================

        self.sheet_filter = SheetFilter(
            remove_empty_sheets=True,
            remove_hidden_sheets=(
                not include_hidden_sheets
            ),
            remove_very_hidden_sheets=(
                not include_very_hidden_sheets
            ),
            exclude_default_names=(
                exclude_default_sheet_names
            ),
            minimum_non_empty_rows=1,
        )

        self.row_filter = RowFilter(
            remove_empty_rows=True,
            remove_duplicate_rows=(
                remove_duplicate_rows
            ),
            remove_error_only_rows=True,
            remove_comment_rows=(
                remove_comment_rows
            ),
            remove_summary_rows=(
                remove_summary_rows
            ),
            minimum_non_empty_cells=1,
            minimum_text_length=1,
            duplicate_scope="sheet",
            case_sensitive_duplicates=False,
            strip_cells=True,
            collapse_internal_spaces=True,
            rebuild_pages=True,
            reassign_block_order=True,
        )

        self.content_filter = ContentFilter()

        # =====================
        # Parser
        # =====================

        self.parser = XLSXParser(
            first_row_as_header=(
                first_row_as_header
            ),
            detect_multiple_regions=(
                detect_multiple_regions
            ),
            maximum_row_gap=maximum_row_gap,
            include_header_in_content=(
                include_header_in_content
            ),
            include_single_row_regions=True,
        )

        # =====================
        # Common Processors
        # =====================

        self.deduplicator = Deduplicator()

        self.section_hierarchy = (
            SectionHierarchyBuilder()
        )

        self.sort_order_assigner = (
            SortOrderAssigner()
        )

        self.chunker = Chunker(
            max_length=chunk_max_length
        )

        self.token_counter = TokenCounter()

        # =====================
        # Output
        # =====================

        self.builder = JsonBuilder()
        self.storage = PostgresStorage()

    def run(
        self,
        file_path: str | Path,
        output: str | Path,
    ):
        """
        执行 XLSX 摄取。

        Args:
            file_path:
                XLSX 输入路径。

            output:
                JSON 输出路径。

        Returns:
            解析、过滤、分块并完成 Token 统计后的 Document。
        """

        input_path = self._validate_input_path(
            file_path
        )

        output_path = Path(
            output
        ).expanduser()

        try:
            # =====================
            # 1. Load
            # =====================

            document = self.loader.load(
                str(input_path)
            )

            # =====================
            # 2. Unicode Normalize
            # =====================

            document = (
                self.unicode_normalizer.process(
                    document
                )
            )

            # =====================
            # 3. Sheet Filter
            # =====================

            document = self.sheet_filter.filter(
                document
            )

            # =====================
            # 4. Row Filter
            # =====================

            document = self.row_filter.filter(
                document
            )

            # =====================
            # 5. Parse
            # =====================

            document = self.parser.parse(
                document
            )

            # =====================
            # 6. Deduplicate
            # =====================

            document = self.deduplicator.process(
                document
            )

            # =====================
            # 7. Section Hierarchy
            # =====================

            document = (
                self.section_hierarchy.process(
                    document
                )
            )

            # =====================
            # 8. Sort Order
            # =====================

            document = (
                self.sort_order_assigner.process(
                    document
                )
            )

            # =====================
            # 9. Content Filter
            # =====================

            document = self.content_filter.filter(
                document
            )

            # =====================
            # 10. Chunk
            # =====================

            document = self.chunker.process(
                document
            )

            # =====================
            # 11. Token Count
            # =====================

            document = self.token_counter.process(
                document
            )

            # =====================
            # 12. Metadata
            # =====================

            document.metadata.update(
                {
                    "pipeline": "XLSXPipeline",
                    "pipeline_status": "SUCCESS",
                    "chapter_count": len(
                        document.chapters
                    ),
                    "section_count": len(
                        document.sections
                    ),
                    "content_count": len(
                        document.contents
                    ),
                    "page_count": len(
                        document.pages
                    ),
                    "block_count": len(
                        document.blocks
                    ),
                }
            )

            # =====================
            # 13. JSON
            # =====================

            if self.save_json_enabled:
                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                json_data = self.builder.build(
                    document
                )

                self.builder.save(
                    json_data,
                    str(output_path),
                )

            # =====================
            # 14. PostgreSQL
            # =====================

            if self.save_database_enabled:
                self.storage.save(
                    document
                )

            return document

        except Exception as exc:
            raise RuntimeError(
                f"XLSX pipeline failed for "
                f"'{input_path.name}': {exc}"
            ) from exc

    @staticmethod
    def _validate_input_path(
        file_path: str | Path,
    ) -> Path:

        path = Path(
            file_path
        ).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"XLSX file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        if path.name.startswith("~$"):
            raise ValueError(
                "Temporary Excel file is not supported: "
                f"{path.name}"
            )

        if path.suffix.lower() != ".xlsx":
            raise ValueError(
                "XLSXPipeline only accepts .xlsx files. "
                f"Received: "
                f"{path.suffix or '<no extension>'}"
            )

        return path