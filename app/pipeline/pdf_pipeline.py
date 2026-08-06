from __future__ import annotations

from pathlib import Path

from app.builder.json_builder import JsonBuilder

from app.filter.common.content_filter import ContentFilter
from app.filter.pdf.header_footer_filter import HeaderFooterFilter
from app.filter.pdf.page_filter import PageFilter

from app.loader.pdf_loader import PDFLoader

from app.parser.pdf_parser import PDFParser

from app.processor.chunker import Chunker
from app.processor.deduplicator import Deduplicator
from app.processor.section_hierarchy import SectionHierarchyBuilder
from app.processor.sort_order_assigner import SortOrderAssigner
from app.processor.token_counter import TokenCounter

from app.storage.postgres_storage import PostgresStorage


class PDFPipeline:
    """
    PDF 文档摄取 Pipeline。

    流程：
        1. 加载 PDF
        2. 过滤空页和目录页
        3. 清理页眉页脚
        4. 解析章节、节和正文
        5. 去重
        6. 建立 Section 层级
        7. 分配排序字段
        8. 清理无效正文
        9. Chunk 分块
        10. 统计最终 Chunk token
        11. 输出 JSON
        12. 保存 PostgreSQL
    """

    def __init__(
        self,
        *,
        chunk_max_length: int = 1000,
        save_json: bool = True,
        save_database: bool = True,
    ) -> None:

        if chunk_max_length <= 0:
            raise ValueError(
                "chunk_max_length must be greater than 0."
            )

        self.save_json_enabled = save_json
        self.save_database_enabled = save_database

        # =====================
        # Loader
        # =====================

        self.loader = PDFLoader()

        # =====================
        # PDF Filters
        # =====================

        self.page_filter = PageFilter()
        self.header_footer_filter = HeaderFooterFilter()
        self.content_filter = ContentFilter()

        # =====================
        # Parser
        # =====================

        self.parser = PDFParser()

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
        执行 PDF 摄取。

        Args:
            file_path:
                PDF 输入路径。

            output:
                JSON 输出路径。

        Returns:
            完成解析、分块和 token 统计后的 Document。
        """

        input_path = self._validate_input_path(
            file_path
        )

        output_path = Path(output)

        try:
            # =====================
            # 1. Load
            # =====================

            document = self.loader.load(
                str(input_path)
            )

            # =====================
            # 2. Page Filter
            # =====================

            document = self.page_filter.filter(
                document
            )

            # =====================
            # 3. Header / Footer
            # =====================

            document = (
                self.header_footer_filter.filter(
                    document
                )
            )

            # =====================
            # 4. Parse
            # =====================

            document = self.parser.parse(
                document
            )

            # =====================
            # 5. Deduplicate
            # =====================

            document = self.deduplicator.process(
                document
            )

            # =====================
            # 6. Section Hierarchy
            # =====================

            document = (
                self.section_hierarchy.process(
                    document
                )
            )

            # =====================
            # 7. Sort Order
            # =====================

            document = (
                self.sort_order_assigner.process(
                    document
                )
            )

            # =====================
            # 8. Content Filter
            # =====================

            document = self.content_filter.filter(
                document
            )

            # =====================
            # 9. Chunk
            # =====================

            document = self.chunker.process(
                document
            )

            # =====================
            # 10. Token Count
            # =====================

            document = self.token_counter.process(
                document
            )

            # =====================
            # 11. Metadata
            # =====================

            document.metadata.update(
                {
                    "pipeline": "PDFPipeline",
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
                }
            )

            # =====================
            # 12. JSON
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
            # 13. PostgreSQL
            # =====================

            if self.save_database_enabled:
                self.storage.save(
                    document
                )

            return document

        except Exception as exc:
            raise RuntimeError(
                f"PDF pipeline failed for "
                f"'{input_path.name}': {exc}"
            ) from exc

    @staticmethod
    def _validate_input_path(
        file_path: str | Path,
    ) -> Path:

        path = Path(file_path).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"PDF file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        if path.suffix.lower() != ".pdf":
            raise ValueError(
                "PDFPipeline only accepts .pdf files. "
                f"Received: {path.suffix or '<no extension>'}"
            )

        return path