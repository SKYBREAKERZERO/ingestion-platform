from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.model.block import DocumentBlock
from app.model.document import Document
from app.model.page import Page


class SlideFilterError(RuntimeError):
    """PPTX Slide 过滤异常。"""


class SlideFilter:
    """
    PPTX Slide 过滤器。

    负责：
        - 删除隐藏 Slide
        - 删除空 Slide
        - 删除 Block 数过少的 Slide
        - 删除文本长度过短的 Slide
        - 根据标题白名单/黑名单过滤 Slide
        - 根据标题正则排除封面、目录、修订履历等页面
        - 删除对应 DocumentBlock
        - 重建逻辑 Page
        - 重新分配 Block order
        - 修正 Block page_number
        - 更新 document.metadata["slides"]

    不负责：
        - Shape 内容清洗
        - 文本框去重
        - 表格行过滤
        - Chapter / Section 建模
        - Chunk
        - Token 统计
    """

    DEFAULT_EXCLUDED_TITLE_PATTERNS = (
        re.compile(
            r"^(?:cover|title|表紙|封面)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:table\s+of\s+contents|contents?|toc|目次|目录)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:revision\s+history|change\s+history|"
            r"改訂履歴|変更履歴|改版履歴|变更履历)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:template|テンプレート|模板)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:sample|サンプル|示例)$",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        *,
        remove_hidden_slides: bool = True,
        remove_empty_slides: bool = True,
        minimum_block_count: int = 1,
        minimum_text_length: int = 1,
        include_slide_numbers: Iterable[int] | None = None,
        exclude_slide_numbers: Iterable[int] | None = None,
        include_titles: Iterable[str] | None = None,
        exclude_titles: Iterable[str] | None = None,
        exclude_default_titles: bool = False,
        exclude_title_patterns: Iterable[
            str | re.Pattern[str]
        ] | None = None,
        case_sensitive: bool = False,
        retain_slides_without_metadata: bool = True,
        rebuild_pages: bool = True,
        reassign_block_order: bool = True,
    ) -> None:

        if minimum_block_count < 0:
            raise ValueError(
                "minimum_block_count cannot be negative."
            )

        if minimum_text_length < 0:
            raise ValueError(
                "minimum_text_length cannot be negative."
            )

        self.remove_hidden_slides = (
            remove_hidden_slides
        )

        self.remove_empty_slides = (
            remove_empty_slides
        )

        self.minimum_block_count = (
            minimum_block_count
        )

        self.minimum_text_length = (
            minimum_text_length
        )

        self.case_sensitive = (
            case_sensitive
        )

        self.retain_slides_without_metadata = (
            retain_slides_without_metadata
        )

        self.rebuild_pages = (
            rebuild_pages
        )

        self.reassign_block_order = (
            reassign_block_order
        )

        self.include_slide_numbers = {
            int(value)
            for value in (
                include_slide_numbers
                or []
            )
        }

        self.exclude_slide_numbers = {
            int(value)
            for value in (
                exclude_slide_numbers
                or []
            )
        }

        self.include_titles = (
            self._normalize_text_set(
                include_titles
            )
        )

        self.exclude_titles = (
            self._normalize_text_set(
                exclude_titles
            )
        )

        patterns: list[
            re.Pattern[str]
        ] = []

        if exclude_default_titles:
            patterns.extend(
                self.DEFAULT_EXCLUDED_TITLE_PATTERNS
            )

        if exclude_title_patterns:
            flags = (
                0
                if case_sensitive
                else re.IGNORECASE
            )

            for pattern in exclude_title_patterns:
                if isinstance(
                    pattern,
                    re.Pattern,
                ):
                    patterns.append(
                        pattern
                    )
                else:
                    patterns.append(
                        re.compile(
                            str(pattern),
                            flags,
                        )
                    )

        self.exclude_title_patterns = tuple(
            patterns
        )

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        try:
            slide_records = (
                self._collect_slide_records(
                    document
                )
            )

            blocks_by_slide = (
                self._group_blocks_by_slide(
                    document.blocks
                )
            )

            retained_slide_indexes: set[
                int
            ] = set()

            removed_slides: list[
                dict[str, Any]
            ] = []

            for record in slide_records:
                slide_index = int(
                    record["slide_index"]
                )

                slide_blocks = (
                    blocks_by_slide.get(
                        slide_index,
                        [],
                    )
                )

                keep, reason = (
                    self._should_keep_slide(
                        record=record,
                        blocks=slide_blocks,
                    )
                )

                if keep:
                    retained_slide_indexes.add(
                        slide_index
                    )

                else:
                    removed_slides.append(
                        {
                            "slide_index": (
                                slide_index
                            ),
                            "slide_number": (
                                record.get(
                                    "slide_number",
                                    slide_index + 1,
                                )
                            ),
                            "title": (
                                record.get(
                                    "title"
                                )
                            ),
                            "hidden": bool(
                                record.get(
                                    "hidden",
                                    False,
                                )
                            ),
                            "reason": reason,
                        }
                    )

            original_block_count = len(
                document.blocks
            )

            document.blocks = [
                block
                for block in document.blocks
                if self._block_is_retained(
                    block=block,
                    retained_slide_indexes=(
                        retained_slide_indexes
                    ),
                )
            ]

            if self.reassign_block_order:
                self._reassign_block_order(
                    document
                )

            if self.rebuild_pages:
                self._rebuild_pages(
                    document=document,
                    retained_slide_indexes=(
                        retained_slide_indexes
                    ),
                    slide_records=slide_records,
                )

            self._update_slide_metadata(
                document=document,
                retained_slide_indexes=(
                    retained_slide_indexes
                ),
                removed_slides=removed_slides,
            )

            document.metadata.update(
                {
                    "slide_filter": (
                        "SlideFilter"
                    ),
                    "slide_filter_status": (
                        "SUCCESS"
                    ),
                    "slide_filter_original_count": (
                        len(slide_records)
                    ),
                    "slide_filter_retained_count": (
                        len(
                            retained_slide_indexes
                        )
                    ),
                    "slide_filter_removed_count": (
                        len(removed_slides)
                    ),
                    "slide_filter_removed_block_count": (
                        original_block_count
                        - len(document.blocks)
                    ),
                    "slide_filter_removed_slides": (
                        removed_slides
                    ),
                }
            )

            return document

        except Exception as exc:
            raise SlideFilterError(
                f"Failed to filter PPTX slides: {exc}"
            ) from exc

    def _should_keep_slide(
        self,
        *,
        record: dict[str, Any],
        blocks: list[DocumentBlock],
    ) -> tuple[bool, str | None]:

        slide_index = int(
            record.get(
                "slide_index",
                0,
            )
        )

        slide_number = int(
            record.get(
                "slide_number",
                slide_index + 1,
            )
        )

        hidden = bool(
            record.get(
                "hidden",
                False,
            )
        )

        title = self._normalize_text(
            record.get(
                "title",
                "",
            )
        )

        normalized_title = (
            self._normalize_key(
                title
            )
        )

        block_count = len(
            blocks
        )

        text_length = sum(
            len(
                self._normalize_text(
                    block.text
                )
            )
            for block in blocks
        )

        # =====================
        # Explicit include
        # =====================

        if (
            self.include_slide_numbers
            and slide_number
            not in self.include_slide_numbers
        ):
            return (
                False,
                "not_in_slide_number_include_list",
            )

        if (
            self.include_titles
            and normalized_title
            not in self.include_titles
        ):
            return (
                False,
                "not_in_title_include_list",
            )

        # =====================
        # Explicit exclude
        # =====================

        if (
            slide_number
            in self.exclude_slide_numbers
        ):
            return (
                False,
                "excluded_slide_number",
            )

        if (
            normalized_title
            in self.exclude_titles
        ):
            return (
                False,
                "excluded_slide_title",
            )

        # =====================
        # Hidden
        # =====================

        if (
            hidden
            and self.remove_hidden_slides
        ):
            return (
                False,
                "hidden_slide",
            )

        # =====================
        # Empty / insufficient
        # =====================

        if (
            self.remove_empty_slides
            and block_count == 0
        ):
            return (
                False,
                "empty_slide",
            )

        if (
            block_count
            < self.minimum_block_count
        ):
            return (
                False,
                "insufficient_block_count",
            )

        if (
            text_length
            < self.minimum_text_length
        ):
            return (
                False,
                "insufficient_text_length",
            )

        # =====================
        # Title pattern
        # =====================

        if (
            title
            and self._matches_excluded_title_pattern(
                title
            )
        ):
            return (
                False,
                "excluded_title_pattern",
            )

        return (
            True,
            None,
        )

    def _collect_slide_records(
        self,
        document: Document,
    ) -> list[dict[str, Any]]:
        """
        优先从 metadata["slides"] 获取。

        metadata 不完整时，从 blocks 回退生成。
        """

        raw_records = document.metadata.get(
            "slides",
            [],
        )

        records: list[
            dict[str, Any]
        ] = []

        if isinstance(
            raw_records,
            list,
        ):
            for raw_record in raw_records:
                if not isinstance(
                    raw_record,
                    dict,
                ):
                    continue

                if (
                    "slide_index"
                    not in raw_record
                ):
                    continue

                record = dict(
                    raw_record
                )

                slide_index = int(
                    record[
                        "slide_index"
                    ]
                )

                record.setdefault(
                    "slide_number",
                    slide_index + 1,
                )

                record.setdefault(
                    "title",
                    None,
                )

                record.setdefault(
                    "hidden",
                    False,
                )

                records.append(
                    record
                )

        if records:
            return sorted(
                records,
                key=lambda item: int(
                    item["slide_index"]
                ),
            )

        # =====================
        # Fallback from blocks
        # =====================

        slide_map: dict[
            int,
            dict[str, Any],
        ] = {}

        for block in document.blocks:
            metadata = block.metadata or {}

            slide_index = metadata.get(
                "slide_index"
            )

            if slide_index is None:
                if block.page_number is None:
                    continue

                slide_index = (
                    block.page_number - 1
                )

            slide_index = int(
                slide_index
            )

            record = slide_map.setdefault(
                slide_index,
                {
                    "slide_index": (
                        slide_index
                    ),
                    "slide_number": (
                        slide_index + 1
                    ),
                    "title": None,
                    "hidden": False,
                    "block_count": 0,
                    "character_count": 0,
                },
            )

            record[
                "block_count"
            ] += 1

            record[
                "character_count"
            ] += len(
                block.text or ""
            )

            if (
                record["title"] is None
                and block.block_type.value
                == "heading"
                and block.level == 1
                and block.text
            ):
                record[
                    "title"
                ] = block.text

        return [
            slide_map[index]
            for index in sorted(
                slide_map
            )
        ]

    @staticmethod
    def _group_blocks_by_slide(
        blocks: list[DocumentBlock],
    ) -> dict[int, list[DocumentBlock]]:

        groups: dict[
            int,
            list[DocumentBlock],
        ] = {}

        for block in blocks:
            metadata = block.metadata or {}

            slide_index = metadata.get(
                "slide_index"
            )

            if slide_index is None:
                if block.page_number is None:
                    continue

                slide_index = (
                    block.page_number - 1
                )

            slide_index = int(
                slide_index
            )

            groups.setdefault(
                slide_index,
                [],
            ).append(
                block
            )

        return groups

    @staticmethod
    def _block_is_retained(
        *,
        block: DocumentBlock,
        retained_slide_indexes: set[int],
    ) -> bool:

        metadata = block.metadata or {}

        slide_index = metadata.get(
            "slide_index"
        )

        if slide_index is None:
            if block.page_number is None:
                # 无 Slide 信息的 Block 默认保留，
                # 防止误删未知来源数据。
                return True

            slide_index = (
                block.page_number - 1
            )

        return int(
            slide_index
        ) in retained_slide_indexes

    @classmethod
    def _reassign_block_order(
        cls,
        document: Document,
    ) -> None:

        sorted_blocks = sorted(
            document.blocks,
            key=cls._block_sort_key,
        )

        for new_order, block in enumerate(
            sorted_blocks
        ):
            block.order = (
                new_order
            )

        document.blocks = (
            sorted_blocks
        )

    @classmethod
    def _rebuild_pages(
        cls,
        *,
        document: Document,
        retained_slide_indexes: set[int],
        slide_records: list[dict[str, Any]],
    ) -> None:
        """
        每个保留 Slide 对应一个逻辑 Page。

        注意：
            Slide 原始编号保存在 metadata。
            Page.page_number 重新连续编号。
        """

        blocks_by_slide = (
            cls._group_blocks_by_slide(
                document.blocks
            )
        )

        record_map = {
            int(
                record["slide_index"]
            ): record
            for record in slide_records
        }

        rebuilt_pages: list[
            Page
        ] = []

        for logical_page_number, slide_index in enumerate(
            sorted(
                retained_slide_indexes
            ),
            start=1,
        ):
            slide_blocks = sorted(
                blocks_by_slide.get(
                    slide_index,
                    [],
                ),
                key=cls._block_sort_key,
            )

            text = "\n".join(
                block.text.strip()
                for block in slide_blocks
                if (
                    block.text
                    and block.text.strip()
                )
            ).strip()

            rebuilt_pages.append(
                Page(
                    page_number=(
                        logical_page_number
                    ),
                    text=text,
                )
            )

            slide_record = record_map.get(
                slide_index
            )

            original_slide_number = (
                int(
                    slide_record.get(
                        "slide_number",
                        slide_index + 1,
                    )
                )
                if slide_record
                else slide_index + 1
            )

            for block in slide_blocks:
                block.page_number = (
                    logical_page_number
                )

                block.metadata.update(
                    {
                        "logical_page_number": (
                            logical_page_number
                        ),
                        "slide_number": (
                            original_slide_number
                        ),
                    }
                )

        document.pages = rebuilt_pages

    @classmethod
    def _update_slide_metadata(
        cls,
        *,
        document: Document,
        retained_slide_indexes: set[int],
        removed_slides: list[dict[str, Any]],
    ) -> None:

        raw_records = document.metadata.get(
            "slides",
            [],
        )

        updated_records: list[
            dict[str, Any]
        ] = []

        logical_page_number = 1

        if isinstance(
            raw_records,
            list,
        ):
            for record in raw_records:
                if not isinstance(
                    record,
                    dict,
                ):
                    continue

                slide_index = record.get(
                    "slide_index"
                )

                if slide_index is None:
                    continue

                slide_index = int(
                    slide_index
                )

                if (
                    slide_index
                    not in retained_slide_indexes
                ):
                    continue

                updated = dict(
                    record
                )

                updated[
                    "logical_page_number"
                ] = logical_page_number

                updated[
                    "status"
                ] = "SUCCESS"

                updated_records.append(
                    updated
                )

                logical_page_number += 1

        document.metadata[
            "slides"
        ] = updated_records

        document.metadata[
            "processed_slide_count"
        ] = len(
            retained_slide_indexes
        )

        document.metadata[
            "skipped_slide_count"
        ] = (
            int(
                document.metadata.get(
                    "skipped_slide_count",
                    0,
                )
                or 0
            )
            + len(
                removed_slides
            )
        )

        document.metadata[
            "block_count"
        ] = len(
            document.blocks
        )

        document.metadata[
            "page_count"
        ] = len(
            document.pages
        )

        document.metadata[
            "character_count"
        ] = sum(
            len(
                page.text
                or ""
            )
            for page in document.pages
        )

    @staticmethod
    def _block_sort_key(
        block: DocumentBlock,
    ) -> tuple[int, int, int, int]:

        metadata = block.metadata or {}

        slide_index = int(
            metadata.get(
                "slide_index",
                (
                    block.page_number - 1
                    if block.page_number
                    is not None
                    else 0
                ),
            )
        )

        visual_index = int(
            metadata.get(
                "visual_index",
                0,
            )
            or 0
        )

        paragraph_index = int(
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
            paragraph_index,
            block.order,
        )

    def _matches_excluded_title_pattern(
        self,
        title: str,
    ) -> bool:

        return any(
            pattern.search(
                title
            )
            is not None
            for pattern
            in self.exclude_title_patterns
        )

    def _normalize_text_set(
        self,
        values: Iterable[str] | None,
    ) -> set[str]:

        if values is None:
            return set()

        return {
            self._normalize_key(
                value
            )
            for value in values
            if self._normalize_text(
                value
            )
        }

    def _normalize_key(
        self,
        value: Any,
    ) -> str:

        normalized = (
            self._normalize_text(
                value
            )
        )

        if self.case_sensitive:
            return normalized

        return normalized.casefold()

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

        normalized = " ".join(
            normalized.split()
        )

        return normalized.strip()

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
                "SlideFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "pptx":
            raise ValueError(
                "SlideFilter only accepts PPTX documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )