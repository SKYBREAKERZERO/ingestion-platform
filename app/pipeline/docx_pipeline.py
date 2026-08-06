from __future__ import annotations

from pathlib import Path

from app.builder.json_builder import JsonBuilder

from app.filter.common.content_filter import ContentFilter
from app.filter.docx.paragraph_filter import ParagraphFilter
from app.filter.docx.table_filter import TableFilter

from app.loader.docx_loader import DOCXLoader

from app.normalizer.unicode_normalizer import UnicodeNormalizer

from app.parser.docx_parser import DOCXParser

from app.processor.chunker import Chunker
from app.processor.deduplicator import Deduplicator
from app.processor.heading_merger import HeadingMerger
from app.processor.section_hierarchy import SectionHierarchyBuilder
from app.processor.sort_order_assigner import SortOrderAssigner
from app.processor.title_sentence_corrector import TitleSentenceCorrector
from app.processor.token_counter import TokenCounter

from app.storage.postgres_storage import PostgresStorage


class DOCXPipeline:
    """
    DOCX 文档摄取 Pipeline。

    流程：
        1. 加载 DOCX
        2. Unicode 标准化
        3. 清理段落
        4. 清理表格文本
        5. 合并跨行标题
        6. 解析章节、节和正文
        7. 修正标题文本
        8. 去重
        9. 建立 Section 层级
        10. 分配排序字段
        11. 清理无效正文
        12. Chunk 分块
        13. 统计最终 Chunk token
        14. 输出 JSON
        15. 保存 PostgreSQL
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

        self.loader = DOCXLoader()

        # =====================
        # Normalizer
        # =====================

        self.unicode_normalizer = UnicodeNormalizer()

        # =====================
        # DOCX Filters
        # =====================

        self.paragraph_filter = ParagraphFilter()
        self.table_filter = TableFilter()
        self.content_filter = ContentFilter()

        # =====================
        # Parser
        # =====================

        self.parser = DOCXParser()

        # =====================
        # Processors
        # =====================

        self.heading_merger = HeadingMerger()

        self.title_sentence_corrector = (
            TitleSentenceCorrector()
        )

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
            # 2. Unicode Normalize
            # =====================

            document = self.unicode_normalizer.process(
                document
            )

            # =====================
            # 3. Paragraph Filter
            # =====================

            document = self.paragraph_filter.filter(
                document
            )

            # =====================
            # 4. Table Filter
            # =====================

            document = self.table_filter.filter(
                document
            )

            # =====================
            # 5. Heading Merge
            # =====================

            document = self.heading_merger.process(
                document
            )

            # =====================
            # 6. Parse
            # =====================

            document = self.parser.parse(
                document
            )

            # =====================
            # 7. Title Correction
            # =====================

            document = (
                self.title_sentence_corrector.process(
                    document
                )
            )

            # =====================
            # 8. Deduplicate
            # =====================

            document = self.deduplicator.process(
                document
            )

            # =====================
            # 9. Section Hierarchy
            # =====================

            document = (
                self.section_hierarchy.process(
                    document
                )
            )

            # =====================
            # 10. Sort Order
            # =====================

            document = (
                self.sort_order_assigner.process(
                    document
                )
            )

            # =====================
            # 11. Content Filter
            # =====================

            document = self.content_filter.filter(
                document
            )

            # =====================
            # 12. Chunk
            # =====================

            document = self.chunker.process(
                document
            )

            # =====================
            # 13. Token Count
            # =====================

            document = self.token_counter.process(
                document
            )

            # =====================
            # 14. Metadata
            # =====================

            document.metadata.update(
                {
                    "pipeline": "DOCXPipeline",
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
            # 15. JSON
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
            # 16. PostgreSQL
            # =====================

            if self.save_database_enabled:
                self.storage.save(
                    document
                )

            return document

        except Exception as exc:
            raise RuntimeError(
                f"DOCX pipeline failed for "
                f"'{input_path.name}': {exc}"
            ) from exc

    @staticmethod
    def _validate_input_path(
        file_path: str | Path,
    ) -> Path:

        path = Path(file_path).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"DOCX file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        if path.suffix.lower() != ".docx":
            raise ValueError(
                "DOCXPipeline only accepts .docx files. "
                f"Received: {path.suffix or '<no extension>'}"
            )

        return path