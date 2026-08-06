from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.model.block import BlockType, DocumentBlock
from app.model.chapter import Chapter
from app.model.content import Content
from app.model.document import Document
from app.model.section import Section


class XLSXParserError(RuntimeError):
    """XLSX 结构解析异常。"""


class XLSXParser:
    """
    XLSX 结构解析器。

    默认映射：

        Worksheet
            -> Chapter

        Sheet 内连续数据区域
            -> Section

        数据区域第一行
            -> Section 标题或表头

        数据区域后续行
            -> Content

    连续区域判断：

        row 1
        row 2
        row 3
        row 7
        row 8

    将识别为两个区域：

        region 1: row 1-3
        region 2: row 7-8

    不负责：
        - 加载 XLSX
        - 删除隐藏 Sheet
        - 删除空行
        - Unicode 标准化
        - Content Chunk
        - Token 统计
        - JSON / PostgreSQL 保存
    """

    _GENERIC_HEADER_VALUES = {
        "id",
        "no",
        "no.",
        "number",
        "name",
        "title",
        "description",
        "value",
        "type",
        "status",
        "date",
        "comment",
        "remarks",
        "note",
        "項番",
        "番号",
        "名称",
        "項目",
        "内容",
        "説明",
        "値",
        "種別",
        "状態",
        "日付",
        "備考",
        "注記",
        "序号",
        "编号",
        "名称",
        "项目",
        "内容",
        "说明",
        "状态",
        "日期",
        "备注",
    }

    def __init__(
        self,
        *,
        first_row_as_header: bool = True,
        detect_multiple_regions: bool = True,
        maximum_row_gap: int = 1,
        include_header_in_content: bool = True,
        include_single_row_regions: bool = True,
        maximum_section_title_length: int = 200,
        content_row_separator: str = "\n",
        cell_separator: str = " | ",
    ) -> None:

        if maximum_row_gap < 1:
            raise ValueError(
                "maximum_row_gap must be at least 1."
            )

        if maximum_section_title_length <= 0:
            raise ValueError(
                "maximum_section_title_length must be greater than 0."
            )

        if not content_row_separator:
            raise ValueError(
                "content_row_separator cannot be empty."
            )

        if not cell_separator:
            raise ValueError(
                "cell_separator cannot be empty."
            )

        self.first_row_as_header = first_row_as_header
        self.detect_multiple_regions = (
            detect_multiple_regions
        )

        self.maximum_row_gap = maximum_row_gap

        self.include_header_in_content = (
            include_header_in_content
        )

        self.include_single_row_regions = (
            include_single_row_regions
        )

        self.maximum_section_title_length = (
            maximum_section_title_length
        )

        self.content_row_separator = (
            content_row_separator
        )

        self.cell_separator = cell_separator

    def parse(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        # 防止同一个 Document 被重复解析后累积数据。
        document.chapters.clear()
        document.sections.clear()
        document.contents.clear()

        sheet_groups = self._group_blocks_by_sheet(
            document.blocks
        )

        if not sheet_groups:
            raise XLSXParserError(
                "XLSX document contains no parseable sheet blocks."
            )

        parsed_sheet_count = 0
        parsed_region_count = 0
        skipped_region_count = 0
        generated_content_count = 0

        for chapter_order, sheet_index in enumerate(
            sorted(sheet_groups),
            start=1,
        ):
            sheet_blocks = sorted(
                sheet_groups[sheet_index],
                key=self._block_sort_key,
            )

            if not sheet_blocks:
                continue

            sheet_name = self._resolve_sheet_name(
                sheet_blocks,
                sheet_index,
            )

            chapter_id = str(
                chapter_order
            )

            chapter = Chapter(
                id=chapter_id,
                title_jp=sheet_name,
                title_en=None,
                level=1,
                sort_order=chapter_order,
                page_number=self._resolve_page_number(
                    sheet_blocks
                ),
                metadata={
                    "source": "xlsx",
                    "sheet_index": sheet_index,
                    "sheet_name": sheet_name,
                    "block_count": len(
                        sheet_blocks
                    ),
                },
            )

            document.chapters.append(
                chapter
            )

            parsed_sheet_count += 1

            regions = self._split_into_regions(
                sheet_blocks
            )

            section_index = 0

            for region_index, region_blocks in enumerate(
                regions,
                start=1,
            ):
                if not region_blocks:
                    continue

                if (
                    len(region_blocks) == 1
                    and not self.include_single_row_regions
                ):
                    skipped_region_count += 1
                    continue

                section_index += 1

                section_id = (
                    f"{chapter_id}."
                    f"{section_index}"
                )

                header_block = (
                    region_blocks[0]
                    if self.first_row_as_header
                    else None
                )

                section_title = self._build_section_title(
                    sheet_name=sheet_name,
                    region_index=region_index,
                    header_block=header_block,
                )

                section = Section(
                    id=section_id,
                    chapter_id=chapter_id,
                    parent_section_id=None,
                    title_jp=section_title,
                    title_en=None,
                    level=2,
                    sort_order=parsed_region_count + 1,
                    page_number=self._resolve_page_number(
                        region_blocks
                    ),
                    metadata={
                        "source": "xlsx",
                        "sheet_index": sheet_index,
                        "sheet_name": sheet_name,
                        "region_index": region_index,
                        "first_row_number": (
                            self._resolve_row_number(
                                region_blocks[0]
                            )
                        ),
                        "last_row_number": (
                            self._resolve_row_number(
                                region_blocks[-1]
                            )
                        ),
                        "row_count": len(
                            region_blocks
                        ),
                        "header_cells": (
                            list(header_block.cells)
                            if header_block
                            else []
                        ),
                    },
                )

                document.sections.append(
                    section
                )

                parsed_region_count += 1

                content_text = self._build_region_content(
                    region_blocks=region_blocks,
                    header_block=header_block,
                )

                if not content_text:
                    continue

                content = Content(
                    chapter_id=chapter_id,
                    section_id=section_id,
                    text=content_text,
                    page_number=self._resolve_page_number(
                        region_blocks
                    ),
                )

                # 供后续 Chunker 或 JSON 使用。
                if hasattr(
                    content,
                    "metadata",
                ):
                    content.metadata.update(
                        {
                            "source": "xlsx",
                            "sheet_index": sheet_index,
                            "sheet_name": sheet_name,
                            "region_index": region_index,
                            "first_row_number": (
                                self._resolve_row_number(
                                    region_blocks[0]
                                )
                            ),
                            "last_row_number": (
                                self._resolve_row_number(
                                    region_blocks[-1]
                                )
                            ),
                        }
                    )

                document.contents.append(
                    content
                )

                generated_content_count += 1

        document.metadata.update(
            {
                "parser": "XLSXParser",
                "parser_status": "SUCCESS",
                "xlsx_parsed_sheet_count": (
                    parsed_sheet_count
                ),
                "xlsx_parsed_region_count": (
                    parsed_region_count
                ),
                "xlsx_skipped_region_count": (
                    skipped_region_count
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
                "xlsx_generated_content_count": (
                    generated_content_count
                ),
            }
        )

        return document

    # ==================================================
    # Sheet Grouping
    # ==================================================

    @classmethod
    def _group_blocks_by_sheet(
        cls,
        blocks: list[DocumentBlock],
    ) -> dict[int, list[DocumentBlock]]:

        groups: dict[
            int,
            list[DocumentBlock],
        ] = defaultdict(list)

        for block in blocks:
            if block.block_type != BlockType.TABLE:
                continue

            sheet_index = cls._resolve_sheet_index(
                block
            )

            groups[
                sheet_index
            ].append(block)

        return dict(
            groups
        )

    # ==================================================
    # Region Detection
    # ==================================================

    def _split_into_regions(
        self,
        blocks: list[DocumentBlock],
    ) -> list[list[DocumentBlock]]:
        """
        根据原始行号断层识别多个数据区域。

        maximum_row_gap=1：

            row 1 -> row 2
                同一区域

            row 2 -> row 4
                新区域
        """

        if not blocks:
            return []

        if not self.detect_multiple_regions:
            return [
                blocks
            ]

        regions: list[
            list[DocumentBlock]
        ] = []

        current_region: list[
            DocumentBlock
        ] = []

        previous_row_number: int | None = None

        for block in blocks:
            row_number = self._resolve_row_number(
                block
            )

            if (
                previous_row_number is not None
                and row_number - previous_row_number
                > self.maximum_row_gap
            ):
                if current_region:
                    regions.append(
                        current_region
                    )

                current_region = []

            current_region.append(
                block
            )

            previous_row_number = row_number

        if current_region:
            regions.append(
                current_region
            )

        return regions

    # ==================================================
    # Section Title
    # ==================================================

    def _build_section_title(
        self,
        *,
        sheet_name: str,
        region_index: int,
        header_block: DocumentBlock | None,
    ) -> str:

        if header_block is None:
            return (
                f"{sheet_name} - "
                f"Table {region_index}"
            )

        header_cells = [
            self._normalize_text(cell)
            for cell in header_block.cells
            if self._normalize_text(cell)
        ]

        if not header_cells:
            return (
                f"{sheet_name} - "
                f"Table {region_index}"
            )

        header_text = self.cell_separator.join(
            header_cells
        )

        if (
            len(header_text)
            > self.maximum_section_title_length
        ):
            header_text = (
                header_text[
                    :self.maximum_section_title_length
                ].rstrip()
                + "..."
            )

        if self._looks_like_header(
            header_cells
        ):
            return header_text

        # 第一行不明显是表头时，也保留其内容，
        # 但加上 Sheet 名，避免 Section 标题语义不明。
        return (
            f"{sheet_name} - "
            f"{header_text}"
        )

    @classmethod
    def _looks_like_header(
        cls,
        cells: list[str],
    ) -> bool:

        if not cells:
            return False

        normalized_cells = [
            cell.strip().casefold()
            for cell in cells
            if cell.strip()
        ]

        if not normalized_cells:
            return False

        generic_match_count = sum(
            1
            for cell in normalized_cells
            if cell in cls._GENERIC_HEADER_VALUES
        )

        if generic_match_count > 0:
            return True

        # 多列、短文本通常更像表头。
        if (
            len(normalized_cells) >= 2
            and all(
                len(cell) <= 50
                for cell in normalized_cells
            )
        ):
            return True

        return False

    # ==================================================
    # Content
    # ==================================================

    def _build_region_content(
        self,
        *,
        region_blocks: list[DocumentBlock],
        header_block: DocumentBlock | None,
    ) -> str:

        if not region_blocks:
            return ""

        content_blocks = list(
            region_blocks
        )

        if (
            header_block is not None
            and not self.include_header_in_content
        ):
            content_blocks = (
                content_blocks[1:]
            )

        if not content_blocks:
            return ""

        header_cells = (
            list(header_block.cells)
            if header_block is not None
            else []
        )

        rows: list[str] = []

        for block in content_blocks:
            row_text = self._format_content_row(
                block=block,
                header_cells=header_cells,
                is_header=(
                    header_block is not None
                    and block is header_block
                ),
            )

            if row_text:
                rows.append(
                    row_text
                )

        return self.content_row_separator.join(
            rows
        ).strip()

    def _format_content_row(
        self,
        *,
        block: DocumentBlock,
        header_cells: list[str],
        is_header: bool,
    ) -> str:

        cells = [
            self._normalize_text(cell)
            for cell in block.cells
        ]

        if not any(cells):
            return ""

        row_number = self._resolve_row_number(
            block
        )

        if is_header:
            return (
                f"[Header row {row_number}] "
                + self.cell_separator.join(cells)
            )

        # 有表头且列数可对应时，生成键值表达。
        if (
            header_cells
            and len(header_cells) == len(cells)
        ):
            pairs: list[str] = []

            for header, value in zip(
                header_cells,
                cells,
            ):
                normalized_header = (
                    self._normalize_text(
                        header
                    )
                )

                if not normalized_header:
                    continue

                if value:
                    pairs.append(
                        f"{normalized_header}: {value}"
                    )

            if pairs:
                return (
                    f"[Row {row_number}] "
                    + self.cell_separator.join(
                        pairs
                    )
                )

        return (
            f"[Row {row_number}] "
            + self.cell_separator.join(cells)
        )

    # ==================================================
    # Resolvers
    # ==================================================

    @staticmethod
    def _resolve_sheet_index(
        block: DocumentBlock,
    ) -> int:

        metadata = block.metadata or {}

        sheet_index = metadata.get(
            "sheet_index"
        )

        if sheet_index is None:
            sheet_index = block.table_index

        if sheet_index is None:
            return 0

        return int(
            sheet_index
        )

    @classmethod
    def _resolve_sheet_name(
        cls,
        blocks: list[DocumentBlock],
        sheet_index: int,
    ) -> str:

        for block in blocks:
            metadata = block.metadata or {}

            sheet_name = metadata.get(
                "sheet_name"
            )

            if sheet_name:
                normalized = cls._normalize_text(
                    str(sheet_name)
                )

                if normalized:
                    return normalized

        return f"Sheet {sheet_index + 1}"

    @staticmethod
    def _resolve_row_number(
        block: DocumentBlock,
    ) -> int:

        metadata = block.metadata or {}

        row_number = metadata.get(
            "row_number"
        )

        if row_number is not None:
            return int(
                row_number
            )

        if block.row_index is not None:
            return int(
                block.row_index
            ) + 1

        return block.order + 1

    @staticmethod
    def _resolve_page_number(
        blocks: list[DocumentBlock],
    ) -> int | None:

        for block in blocks:
            if block.page_number is not None:
                return block.page_number

        return None

    @classmethod
    def _block_sort_key(
        cls,
        block: DocumentBlock,
    ) -> tuple[int, int]:

        return (
            cls._resolve_row_number(
                block
            ),
            block.order,
        )

    # ==================================================
    # Text
    # ==================================================

    @staticmethod
    def _normalize_text(
        text: Any,
    ) -> str:

        if text is None:
            return ""

        normalized = str(
            text
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

        normalized = " / ".join(
            " ".join(line.split())
            for line in normalized.splitlines()
            if line.strip()
        )

        return normalized.strip()

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
                "XLSXParser expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "xlsx":
            raise ValueError(
                "XLSXParser only accepts XLSX documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )

        if not document.blocks:
            raise ValueError(
                "XLSX document contains no blocks."
            )

        if not any(
            block.block_type == BlockType.TABLE
            and (
                block.text.strip()
                or any(
                    str(cell).strip()
                    for cell in block.cells
                )
            )
            for block in document.blocks
        ):
            raise ValueError(
                "XLSX document contains no extractable rows."
            )