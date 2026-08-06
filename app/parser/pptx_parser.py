from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.model.block import BlockType, DocumentBlock
from app.model.chapter import Chapter
from app.model.content import Content
from app.model.document import Document
from app.model.section import Section


class PPTXParserError(RuntimeError):
    """PPTX 结构解析异常。"""


class PPTXParser:
    """
    PPTX 结构解析器。

    默认结构映射：

        Slide
            -> Chapter

        Slide Title
            -> Chapter Title

        Subtitle / Secondary Heading
            -> Section

        Paragraph / List / TextBox / Table / Chart / Image Caption
            -> Content

    设计原则：
        - 每张保留的 Slide 至少生成一个 Chapter
        - Slide 原始编号优先作为 Chapter ID
        - 没有标题的 Slide 使用首个有效文本或默认标题
        - 没有 Section 的正文保留为 Chapter 级 Content
        - 表格按行转为结构化文本
        - 图片和图表仅在有可检索文本时进入 Content
        - 不在 Parser 内进行 Chunk 和 Token 统计
    """

    _CONTENT_BLOCK_TYPES = {
        BlockType.PARAGRAPH,
        BlockType.LIST,
        BlockType.TEXTBOX,
        BlockType.TABLE,
        BlockType.IMAGE,
        BlockType.UNKNOWN,
    }

    def __init__(
        self,
        *,
        use_original_slide_number_as_chapter_id: bool = True,
        create_section_from_secondary_heading: bool = True,
        create_default_section_when_missing: bool = False,
        include_slide_title_in_content: bool = False,
        include_secondary_heading_in_content: bool = False,
        include_image_blocks: bool = True,
        include_chart_blocks: bool = True,
        include_table_headers: bool = True,
        merge_adjacent_content_blocks: bool = True,
        content_separator: str = "\n",
        table_cell_separator: str = " | ",
        default_slide_title_prefix: str = "Slide",
        maximum_title_length: int = 300,
    ) -> None:

        if not content_separator:
            raise ValueError(
                "content_separator cannot be empty."
            )

        if not table_cell_separator:
            raise ValueError(
                "table_cell_separator cannot be empty."
            )

        if not default_slide_title_prefix.strip():
            raise ValueError(
                "default_slide_title_prefix cannot be empty."
            )

        if maximum_title_length <= 0:
            raise ValueError(
                "maximum_title_length must be greater than 0."
            )

        self.use_original_slide_number_as_chapter_id = (
            use_original_slide_number_as_chapter_id
        )

        self.create_section_from_secondary_heading = (
            create_section_from_secondary_heading
        )

        self.create_default_section_when_missing = (
            create_default_section_when_missing
        )

        self.include_slide_title_in_content = (
            include_slide_title_in_content
        )

        self.include_secondary_heading_in_content = (
            include_secondary_heading_in_content
        )

        self.include_image_blocks = include_image_blocks
        self.include_chart_blocks = include_chart_blocks
        self.include_table_headers = include_table_headers

        self.merge_adjacent_content_blocks = (
            merge_adjacent_content_blocks
        )

        self.content_separator = content_separator
        self.table_cell_separator = table_cell_separator

        self.default_slide_title_prefix = (
            default_slide_title_prefix.strip()
        )

        self.maximum_title_length = maximum_title_length

    def parse(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        document.chapters.clear()
        document.sections.clear()
        document.contents.clear()

        blocks_by_slide = self._group_blocks_by_slide(
            document.blocks
        )

        slide_records = self._collect_slide_records(
            document
        )

        if not blocks_by_slide and not slide_records:
            raise PPTXParserError(
                "PPTX document contains no parseable slides."
            )

        slide_indexes = sorted(
            set(blocks_by_slide)
            | set(slide_records)
        )

        parsed_slide_count = 0
        generated_section_count = 0
        generated_content_count = 0
        chapter_root_content_count = 0
        skipped_empty_content_count = 0

        global_section_order = 0

        for chapter_order, slide_index in enumerate(
            slide_indexes,
            start=1,
        ):
            slide_blocks = sorted(
                blocks_by_slide.get(
                    slide_index,
                    [],
                ),
                key=self._block_sort_key,
            )

            slide_record = slide_records.get(
                slide_index,
                {}
            )

            slide_number = self._resolve_slide_number(
                slide_index=slide_index,
                slide_record=slide_record,
                blocks=slide_blocks,
            )

            chapter_id = self._build_chapter_id(
                slide_number=slide_number,
                chapter_order=chapter_order,
            )

            slide_title_block = self._find_slide_title_block(
                slide_blocks
            )

            chapter_title = self._resolve_chapter_title(
                slide_number=slide_number,
                slide_record=slide_record,
                title_block=slide_title_block,
                blocks=slide_blocks,
            )

            page_number = self._resolve_page_number(
                slide_blocks
            )

            chapter = Chapter(
                id=chapter_id,
                title_jp=chapter_title,
                title_en=None,
                level=1,
                sort_order=chapter_order,
                page_number=page_number,
                metadata={
                    "source": "pptx",
                    "slide_index": slide_index,
                    "slide_number": slide_number,
                    "logical_page_number": page_number,
                    "block_count": len(slide_blocks),
                    "hidden": bool(
                        slide_record.get(
                            "hidden",
                            False,
                        )
                    ),
                },
            )

            document.chapters.append(
                chapter
            )

            parsed_slide_count += 1

            current_section: Section | None = None
            section_sequence = 0

            content_buffer: list[str] = []
            content_page_number = page_number

            def save_content() -> None:
                nonlocal content_buffer
                nonlocal generated_content_count
                nonlocal chapter_root_content_count
                nonlocal skipped_empty_content_count

                text = self.content_separator.join(
                    content_buffer
                ).strip()

                content_buffer = []

                if not text:
                    skipped_empty_content_count += 1
                    return

                section_id = (
                    current_section.id
                    if current_section is not None
                    else None
                )

                document.contents.append(
                    Content(
                        chapter_id=chapter_id,
                        section_id=section_id,
                        text=text,
                        page_number=content_page_number,
                    )
                )

                generated_content_count += 1

                if section_id is None:
                    chapter_root_content_count += 1

            for block in slide_blocks:
                if block is slide_title_block:
                    if self.include_slide_title_in_content:
                        title_text = self._normalize_text(
                            block.text
                        )

                        if title_text:
                            content_buffer.append(
                                title_text
                            )

                    continue

                if self._is_secondary_heading(
                    block
                ):
                    save_content()

                    if not self.create_section_from_secondary_heading:
                        if self.include_secondary_heading_in_content:
                            heading_text = self._normalize_text(
                                block.text
                            )

                            if heading_text:
                                content_buffer.append(
                                    heading_text
                                )

                        continue

                    section_sequence += 1
                    global_section_order += 1

                    section_id = (
                        f"{chapter_id}."
                        f"{section_sequence}"
                    )

                    section_title = self._normalize_title(
                        block.text
                    )

                    if not section_title:
                        section_title = (
                            f"{chapter_title} - "
                            f"Section {section_sequence}"
                        )

                    current_section = Section(
                        id=section_id,
                        chapter_id=chapter_id,
                        parent_section_id=None,
                        title_jp=section_title,
                        title_en=None,
                        level=2,
                        sort_order=global_section_order,
                        page_number=(
                            block.page_number
                            or page_number
                        ),
                        metadata={
                            "source": "pptx",
                            "slide_index": slide_index,
                            "slide_number": slide_number,
                            "shape_index": (
                                block.metadata.get(
                                    "shape_index"
                                )
                            ),
                            "visual_index": (
                                block.metadata.get(
                                    "visual_index"
                                )
                            ),
                            "block_id": block.id,
                        },
                    )

                    document.sections.append(
                        current_section
                    )

                    generated_section_count += 1

                    if self.include_secondary_heading_in_content:
                        content_buffer.append(
                            section_title
                        )

                    continue

                content_text = self._build_content_text(
                    block
                )

                if not content_text:
                    continue

                content_page_number = (
                    block.page_number
                    or page_number
                )

                if self.merge_adjacent_content_blocks:
                    content_buffer.append(
                        content_text
                    )

                else:
                    save_content()

                    content_buffer.append(
                        content_text
                    )

                    save_content()

            save_content()

            if (
                self.create_default_section_when_missing
                and section_sequence == 0
            ):
                default_section_id = (
                    f"{chapter_id}.1"
                )

                default_section = Section(
                    id=default_section_id,
                    chapter_id=chapter_id,
                    parent_section_id=None,
                    title_jp=chapter_title,
                    title_en=None,
                    level=2,
                    sort_order=(
                        global_section_order + 1
                    ),
                    page_number=page_number,
                    metadata={
                        "source": "pptx",
                        "slide_index": slide_index,
                        "slide_number": slide_number,
                        "generated": True,
                        "reason": (
                            "slide_without_secondary_heading"
                        ),
                    },
                )

                document.sections.append(
                    default_section
                )

                global_section_order += 1
                generated_section_count += 1

                for content in document.contents:
                    if (
                        content.chapter_id == chapter_id
                        and not content.section_id
                    ):
                        content.section_id = (
                            default_section_id
                        )

        document.metadata.update(
            {
                "parser": "PPTXParser",
                "parser_status": "SUCCESS",
                "pptx_parsed_slide_count": (
                    parsed_slide_count
                ),
                "pptx_generated_section_count": (
                    generated_section_count
                ),
                "pptx_generated_content_count": (
                    generated_content_count
                ),
                "pptx_chapter_root_content_count": (
                    chapter_root_content_count
                ),
                "pptx_skipped_empty_content_count": (
                    skipped_empty_content_count
                ),
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

        return document

    # ==================================================
    # Content conversion
    # ==================================================

    def _build_content_text(
        self,
        block: DocumentBlock,
    ) -> str:

        if block.block_type not in self._CONTENT_BLOCK_TYPES:
            return ""

        content_kind = str(
            block.metadata.get(
                "content_kind",
                "",
            )
        ).strip().lower()

        if (
            block.block_type == BlockType.IMAGE
            and not self.include_image_blocks
        ):
            return ""

        if (
            content_kind == "chart"
            and not self.include_chart_blocks
        ):
            return ""

        if block.block_type == BlockType.TABLE:
            return self._format_table_row(
                block
            )

        if block.block_type == BlockType.IMAGE:
            return self._format_image_block(
                block
            )

        if content_kind == "chart":
            return self._format_chart_block(
                block
            )

        text = self._normalize_text(
            block.text
        )

        if not text:
            return ""

        if block.block_type == BlockType.LIST:
            level = int(
                block.metadata.get(
                    "paragraph_level",
                    block.level
                    or 1,
                )
                or 1
            )

            indentation = "  " * max(
                level - 1,
                0,
            )

            return (
                f"{indentation}- {text}"
            )

        return text

    def _format_table_row(
        self,
        block: DocumentBlock,
    ) -> str:

        cells = [
            self._normalize_text(
                cell
            )
            for cell in block.cells
        ]

        cells = self._trim_empty_boundaries(
            cells
        )

        if not any(cells):
            return ""

        row_index = block.row_index

        is_header_candidate = bool(
            block.metadata.get(
                "is_header_candidate",
                False,
            )
        )

        if (
            is_header_candidate
            and not self.include_table_headers
        ):
            return ""

        row_text = self.table_cell_separator.join(
            cells
        ).strip()

        if not row_text:
            return ""

        if is_header_candidate:
            return (
                f"[Table header] {row_text}"
            )

        if row_index is not None:
            return (
                f"[Table row {row_index + 1}] "
                f"{row_text}"
            )

        return row_text

    @staticmethod
    def _format_image_block(
        block: DocumentBlock,
    ) -> str:

        text = PPTXParser._normalize_text(
            block.text
        )

        image_filename = block.metadata.get(
            "image_filename"
        )

        alt_text = PPTXParser._normalize_text(
            block.metadata.get(
                "alt_text",
                "",
            )
        )

        description = (
            alt_text
            or text
        )

        if description:
            return (
                f"[Image] {description}"
            )

        if image_filename:
            return (
                f"[Image] {image_filename}"
            )

        return ""

    @staticmethod
    def _format_chart_block(
        block: DocumentBlock,
    ) -> str:

        text = PPTXParser._normalize_text(
            block.text
        )

        metadata = block.metadata or {}

        title = PPTXParser._normalize_text(
            metadata.get(
                "chart_title",
                "",
            )
        )

        series = metadata.get(
            "chart_series",
            []
        )

        categories = metadata.get(
            "chart_categories",
            []
        )

        parts: list[str] = []

        if title:
            parts.append(
                f"Chart title: {title}"
            )

        if text:
            parts.append(text)

        if categories:
            parts.append(
                "Categories: "
                + ", ".join(
                    str(value)
                    for value in categories
                )
            )

        if isinstance(series, list):
            for item in series:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                name = item.get(
                    "name"
                )

                values = item.get(
                    "values",
                    []
                )

                if name or values:
                    parts.append(
                        f"Series {name or ''}: "
                        + ", ".join(
                            str(value)
                            for value in values
                        )
                    )

        if not parts:
            return ""

        return (
            "[Chart]\n"
            + "\n".join(parts)
        )

    # ==================================================
    # Slide and chapter
    # ==================================================

    def _build_chapter_id(
        self,
        *,
        slide_number: int,
        chapter_order: int,
    ) -> str:

        if (
            self.use_original_slide_number_as_chapter_id
        ):
            return str(
                slide_number
            )

        return str(
            chapter_order
        )

    def _resolve_chapter_title(
        self,
        *,
        slide_number: int,
        slide_record: dict[str, Any],
        title_block: DocumentBlock | None,
        blocks: list[DocumentBlock],
    ) -> str:

        if title_block is not None:
            title = self._normalize_title(
                title_block.text
            )

            if title:
                return title

        metadata_title = self._normalize_title(
            slide_record.get(
                "title",
                "",
            )
        )

        if metadata_title:
            return metadata_title

        for block in blocks:
            text = self._normalize_title(
                block.text
            )

            if text:
                return text

        return (
            f"{self.default_slide_title_prefix} "
            f"{slide_number}"
        )

    @staticmethod
    def _find_slide_title_block(
        blocks: list[DocumentBlock],
    ) -> DocumentBlock | None:

        for block in blocks:
            if (
                block.block_type
                == BlockType.HEADING
                and block.level == 1
            ):
                return block

        return None

    def _normalize_title(
        self,
        value: Any,
    ) -> str:

        text = self._normalize_text(
            value
        )

        if (
            len(text)
            <= self.maximum_title_length
        ):
            return text

        return (
            text[
                :self.maximum_title_length
            ].rstrip()
            + "..."
        )

    # ==================================================
    # Secondary headings
    # ==================================================

    @staticmethod
    def _is_secondary_heading(
        block: DocumentBlock,
    ) -> bool:

        if block.block_type != BlockType.HEADING:
            return False

        if block.level is None:
            return False

        return block.level >= 2

    # ==================================================
    # Group and records
    # ==================================================

    @classmethod
    def _group_blocks_by_slide(
        cls,
        blocks: list[DocumentBlock],
    ) -> dict[int, list[DocumentBlock]]:

        groups: dict[
            int,
            list[DocumentBlock],
        ] = defaultdict(list)

        for block in blocks:
            slide_index = cls._resolve_slide_index(
                block
            )

            groups[
                slide_index
            ].append(
                block
            )

        return dict(
            groups
        )

    @staticmethod
    def _collect_slide_records(
        document: Document,
    ) -> dict[int, dict[str, Any]]:

        raw_records = document.metadata.get(
            "slides",
            [],
        )

        records: dict[
            int,
            dict[str, Any],
        ] = {}

        if not isinstance(
            raw_records,
            list,
        ):
            return records

        for raw_record in raw_records:
            if not isinstance(
                raw_record,
                dict,
            ):
                continue

            slide_index = raw_record.get(
                "slide_index"
            )

            if slide_index is None:
                continue

            records[
                int(slide_index)
            ] = dict(
                raw_record
            )

        return records

    # ==================================================
    # Resolvers
    # ==================================================

    @staticmethod
    def _resolve_slide_index(
        block: DocumentBlock,
    ) -> int:

        metadata = block.metadata or {}

        slide_index = metadata.get(
            "slide_index"
        )

        if slide_index is not None:
            return int(
                slide_index
            )

        slide_number = metadata.get(
            "slide_number"
        )

        if slide_number is not None:
            return int(
                slide_number
            ) - 1

        if block.page_number is not None:
            return int(
                block.page_number
            ) - 1

        return 0

    @staticmethod
    def _resolve_slide_number(
        *,
        slide_index: int,
        slide_record: dict[str, Any],
        blocks: list[DocumentBlock],
    ) -> int:

        record_number = slide_record.get(
            "slide_number"
        )

        if record_number is not None:
            return int(
                record_number
            )

        for block in blocks:
            value = block.metadata.get(
                "slide_number"
            )

            if value is not None:
                return int(
                    value
                )

        return (
            slide_index + 1
        )

    @staticmethod
    def _resolve_page_number(
        blocks: list[DocumentBlock],
    ) -> int | None:

        for block in blocks:
            if block.page_number is not None:
                return int(
                    block.page_number
                )

        return None

    @classmethod
    def _block_sort_key(
        cls,
        block: DocumentBlock,
    ) -> tuple[int, int, int, int]:

        metadata = block.metadata or {}

        slide_index = cls._resolve_slide_index(
            block
        )

        visual_index = int(
            metadata.get(
                "visual_index",
                0,
            )
            or 0
        )

        paragraph_or_row_index = int(
            metadata.get(
                "paragraph_index",
                metadata.get(
                    "table_row_index",
                    0,
                ),
            )
            or 0
        )

        return (
            slide_index,
            visual_index,
            paragraph_or_row_index,
            block.order,
        )

    # ==================================================
    # Text
    # ==================================================

    @staticmethod
    def _trim_empty_boundaries(
        values: list[str],
    ) -> list[str]:

        if not values:
            return []

        start = 0
        end = len(values)

        while (
            start < end
            and not values[start]
        ):
            start += 1

        while (
            end > start
            and not values[end - 1]
        ):
            end -= 1

        return values[
            start:end
        ]

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        normalized = str(
            value
        )

        normalized = normalized.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        normalized = normalized.replace(
            "\u200b",
            "",
        )

        normalized = normalized.replace(
            "\ufeff",
            "",
        )

        normalized = normalized.replace(
            "\r\n",
            "\n",
        )

        normalized = normalized.replace(
            "\r",
            "\n",
        )

        lines = [
            " ".join(
                line.split()
            )
            for line in normalized.splitlines()
            if line.strip()
        ]

        return "\n".join(
            lines
        ).strip()

    # ==================================================
    # Validation
    # ==================================================

    @staticmethod
    def _validate_document(
        document: Document,
    ) -> None:

        if document is None:
            raise ValueError(
                "Document cannot be None."
            )

        if not isinstance(
            document,
            Document,
        ):
            raise TypeError(
                "PPTXParser expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "pptx":
            raise ValueError(
                "PPTXParser only accepts PPTX documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )

        if not document.pages and not document.blocks:
            raise ValueError(
                "PPTX document contains no pages or blocks."
            )