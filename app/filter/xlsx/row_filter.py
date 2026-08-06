from __future__ import annotations

import re
from collections.abc import Iterable

from app.model.block import BlockType, DocumentBlock
from app.model.document import Document
from app.model.page import Page


class RowFilter:
    """
    XLSX 行过滤器。

    负责：
        - 删除空行
        - 删除仅空白字符的行
        - 删除重复行
        - 可选删除备注、注释、合计、小计行
        - 可选删除只包含 Excel 错误值的行
        - 限制过短或过长行
        - 保留各 Sheet 内行顺序
        - 重建 Document.pages
        - 更新 document.metadata

    不负责：
        - Sheet 过滤
        - 表头识别
        - 表格区域识别
        - Chapter / Section 建模
        - Chunk
        - Token 统计
    """

    _EXCEL_ERROR_VALUES = {
        "#NULL!",
        "#DIV/0!",
        "#VALUE!",
        "#REF!",
        "#NAME?",
        "#NUM!",
        "#N/A",
        "#GETTING_DATA",
        "#SPILL!",
        "#CALC!",
        "#FIELD!",
        "#BLOCKED!",
        "#UNKNOWN!",
    }

    _DEFAULT_COMMENT_PATTERNS = (
        re.compile(
            r"^(?:note|notes|comment|comments)\s*[:：]?",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:備考|注記|注意|メモ|コメント)\s*[:：]?",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:备注|说明|注释|注意事项)\s*[:：]?",
            re.IGNORECASE,
        ),
    )

    _DEFAULT_SUMMARY_PATTERNS = (
        re.compile(
            r"^(?:total|subtotal|grand total)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:合計|小計|総計)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:合计|小计|总计)\b",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        *,
        remove_empty_rows: bool = True,
        remove_duplicate_rows: bool = True,
        remove_error_only_rows: bool = True,
        remove_comment_rows: bool = False,
        remove_summary_rows: bool = False,
        minimum_non_empty_cells: int = 1,
        minimum_text_length: int = 1,
        maximum_text_length: int | None = None,
        duplicate_scope: str = "sheet",
        case_sensitive_duplicates: bool = False,
        strip_cells: bool = True,
        collapse_internal_spaces: bool = True,
        comment_patterns: Iterable[str | re.Pattern[str]]
        | None = None,
        summary_patterns: Iterable[str | re.Pattern[str]]
        | None = None,
        rebuild_pages: bool = True,
        reassign_block_order: bool = True,
    ) -> None:

        if minimum_non_empty_cells < 0:
            raise ValueError(
                "minimum_non_empty_cells cannot be negative."
            )

        if minimum_text_length < 0:
            raise ValueError(
                "minimum_text_length cannot be negative."
            )

        if (
            maximum_text_length is not None
            and maximum_text_length <= 0
        ):
            raise ValueError(
                "maximum_text_length must be greater than 0."
            )

        if (
            maximum_text_length is not None
            and maximum_text_length < minimum_text_length
        ):
            raise ValueError(
                "maximum_text_length cannot be less than "
                "minimum_text_length."
            )

        if duplicate_scope not in {
            "sheet",
            "workbook",
        }:
            raise ValueError(
                "duplicate_scope must be either "
                "'sheet' or 'workbook'."
            )

        self.remove_empty_rows = remove_empty_rows
        self.remove_duplicate_rows = (
            remove_duplicate_rows
        )

        self.remove_error_only_rows = (
            remove_error_only_rows
        )

        self.remove_comment_rows = (
            remove_comment_rows
        )

        self.remove_summary_rows = (
            remove_summary_rows
        )

        self.minimum_non_empty_cells = (
            minimum_non_empty_cells
        )

        self.minimum_text_length = (
            minimum_text_length
        )

        self.maximum_text_length = (
            maximum_text_length
        )

        self.duplicate_scope = duplicate_scope

        self.case_sensitive_duplicates = (
            case_sensitive_duplicates
        )

        self.strip_cells = strip_cells
        self.collapse_internal_spaces = (
            collapse_internal_spaces
        )

        self.rebuild_pages = rebuild_pages
        self.reassign_block_order = (
            reassign_block_order
        )

        self.comment_patterns = (
            self._compile_patterns(
                comment_patterns,
                defaults=self._DEFAULT_COMMENT_PATTERNS,
            )
        )

        self.summary_patterns = (
            self._compile_patterns(
                summary_patterns,
                defaults=self._DEFAULT_SUMMARY_PATTERNS,
            )
        )

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        original_block_count = len(
            document.blocks
        )

        retained_blocks: list[
            DocumentBlock
        ] = []

        workbook_seen: set[str] = set()
        sheet_seen: dict[
            int,
            set[str],
        ] = {}

        removed_empty_count = 0
        removed_duplicate_count = 0
        removed_error_count = 0
        removed_comment_count = 0
        removed_summary_count = 0
        removed_short_count = 0
        removed_long_count = 0
        removed_invalid_type_count = 0

        for block in sorted(
            document.blocks,
            key=self._block_sort_key,
        ):
            if block.block_type != BlockType.TABLE:
                removed_invalid_type_count += 1
                continue

            normalized_cells = [
                self._normalize_cell(
                    cell
                )
                for cell in block.cells
            ]

            normalized_cells = (
                self._trim_empty_boundaries(
                    normalized_cells
                )
            )

            non_empty_cells = [
                cell
                for cell in normalized_cells
                if cell
            ]

            if (
                self.remove_empty_rows
                and not non_empty_cells
            ):
                removed_empty_count += 1
                continue

            if (
                len(non_empty_cells)
                < self.minimum_non_empty_cells
            ):
                removed_empty_count += 1
                continue

            row_text = self._build_row_text(
                normalized_cells
            )

            if (
                len(row_text)
                < self.minimum_text_length
            ):
                removed_short_count += 1
                continue

            if (
                self.maximum_text_length is not None
                and len(row_text)
                > self.maximum_text_length
            ):
                removed_long_count += 1
                continue

            if (
                self.remove_error_only_rows
                and self._is_error_only_row(
                    non_empty_cells
                )
            ):
                removed_error_count += 1
                continue

            if (
                self.remove_comment_rows
                and self._matches_patterns(
                    row_text,
                    self.comment_patterns,
                )
            ):
                removed_comment_count += 1
                continue

            if (
                self.remove_summary_rows
                and self._matches_patterns(
                    row_text,
                    self.summary_patterns,
                )
            ):
                removed_summary_count += 1
                continue

            if self.remove_duplicate_rows:
                duplicate_key = (
                    self._build_duplicate_key(
                        normalized_cells
                    )
                )

                sheet_index = (
                    self._resolve_sheet_index(
                        block
                    )
                )

                if self.duplicate_scope == "workbook":
                    if duplicate_key in workbook_seen:
                        removed_duplicate_count += 1
                        continue

                    workbook_seen.add(
                        duplicate_key
                    )

                else:
                    seen = sheet_seen.setdefault(
                        sheet_index,
                        set(),
                    )

                    if duplicate_key in seen:
                        removed_duplicate_count += 1
                        continue

                    seen.add(
                        duplicate_key
                    )

            updated_block = block.model_copy(
                deep=True
            )

            updated_block.cells = (
                normalized_cells
            )

            updated_block.text = row_text

            updated_block.metadata = {
                **updated_block.metadata,
                "row_filter_status": "RETAINED",
                "non_empty_cell_count": len(
                    non_empty_cells
                ),
                "normalized_column_count": len(
                    normalized_cells
                ),
            }

            retained_blocks.append(
                updated_block
            )

        if self.reassign_block_order:
            for order, block in enumerate(
                retained_blocks
            ):
                block.order = order

        document.blocks = retained_blocks

        if self.rebuild_pages:
            self._rebuild_pages(
                document
            )

        self._update_sheet_metadata(
            document
        )

        document.metadata.update(
            {
                "row_filter": "RowFilter",
                "row_filter_status": "SUCCESS",
                "row_filter_original_block_count": (
                    original_block_count
                ),
                "row_filter_retained_block_count": len(
                    retained_blocks
                ),
                "row_filter_removed_block_count": (
                    original_block_count
                    - len(retained_blocks)
                ),
                "row_filter_removed_empty_count": (
                    removed_empty_count
                ),
                "row_filter_removed_duplicate_count": (
                    removed_duplicate_count
                ),
                "row_filter_removed_error_count": (
                    removed_error_count
                ),
                "row_filter_removed_comment_count": (
                    removed_comment_count
                ),
                "row_filter_removed_summary_count": (
                    removed_summary_count
                ),
                "row_filter_removed_short_count": (
                    removed_short_count
                ),
                "row_filter_removed_long_count": (
                    removed_long_count
                ),
                "row_filter_removed_invalid_type_count": (
                    removed_invalid_type_count
                ),
            }
        )

        return document

    def _normalize_cell(
        self,
        value: str,
    ) -> str:

        normalized = str(
            value or ""
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

        if self.collapse_internal_spaces:
            lines = [
                " ".join(
                    line.split()
                )
                for line in normalized.splitlines()
                if line.strip()
            ]

            normalized = " / ".join(
                lines
            )

        if self.strip_cells:
            normalized = normalized.strip()

        return normalized

    @staticmethod
    def _trim_empty_boundaries(
        cells: list[str],
    ) -> list[str]:

        if not cells:
            return []

        start = 0
        end = len(cells)

        while (
            start < end
            and not cells[start]
        ):
            start += 1

        while (
            end > start
            and not cells[end - 1]
        ):
            end -= 1

        return cells[
            start:end
        ]

    @staticmethod
    def _build_row_text(
        cells: list[str],
    ) -> str:

        return " | ".join(
            cells
        ).strip()

    @classmethod
    def _is_error_only_row(
        cls,
        cells: list[str],
    ) -> bool:

        if not cells:
            return False

        return all(
            cell.upper()
            in cls._EXCEL_ERROR_VALUES
            for cell in cells
        )

    def _build_duplicate_key(
        self,
        cells: list[str],
    ) -> str:

        values = cells

        if not self.case_sensitive_duplicates:
            values = [
                value.casefold()
                for value in values
            ]

        return "\x1f".join(
            values
        )

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
    def _block_sort_key(
        cls,
        block: DocumentBlock,
    ) -> tuple[int, int, int]:

        metadata = block.metadata or {}

        sheet_index = cls._resolve_sheet_index(
            block
        )

        row_number = metadata.get(
            "row_number"
        )

        if row_number is None:
            row_number = (
                block.row_index + 1
                if block.row_index is not None
                else 0
            )

        return (
            sheet_index,
            int(row_number),
            block.order,
        )

    @staticmethod
    def _matches_patterns(
        text: str,
        patterns: tuple[
            re.Pattern[str],
            ...,
        ],
    ) -> bool:

        return any(
            pattern.search(
                text
            )
            is not None
            for pattern in patterns
        )

    @staticmethod
    def _compile_patterns(
        patterns: Iterable[
            str | re.Pattern[str]
        ] | None,
        *,
        defaults: tuple[
            re.Pattern[str],
            ...,
        ],
    ) -> tuple[
        re.Pattern[str],
        ...,
    ]:

        compiled = list(
            defaults
        )

        if patterns is None:
            return tuple(
                compiled
            )

        for pattern in patterns:
            if isinstance(
                pattern,
                re.Pattern,
            ):
                compiled.append(
                    pattern
                )
                continue

            compiled.append(
                re.compile(
                    str(pattern),
                    re.IGNORECASE,
                )
            )

        return tuple(
            compiled
        )

    @classmethod
    def _rebuild_pages(
        cls,
        document: Document,
    ) -> None:
        """
        每个 Sheet 重新构建一个逻辑 Page。
        """

        blocks_by_sheet: dict[
            int,
            list[DocumentBlock],
        ] = {}

        for block in document.blocks:
            sheet_index = (
                cls._resolve_sheet_index(
                    block
                )
            )

            blocks_by_sheet.setdefault(
                sheet_index,
                [],
            ).append(
                block
            )

        rebuilt_pages: list[Page] = []

        for logical_page_number, sheet_index in enumerate(
            sorted(blocks_by_sheet),
            start=1,
        ):
            sheet_blocks = sorted(
                blocks_by_sheet[
                    sheet_index
                ],
                key=cls._block_sort_key,
            )

            text = "\n".join(
                block.text
                for block in sheet_blocks
                if block.text
            ).strip()

            rebuilt_pages.append(
                Page(
                    page_number=(
                        logical_page_number
                    ),
                    text=text,
                )
            )

            for block in sheet_blocks:
                block.page_number = (
                    logical_page_number
                )

        document.pages = rebuilt_pages

    @classmethod
    def _update_sheet_metadata(
        cls,
        document: Document,
    ) -> None:

        sheet_counts: dict[
            int,
            int,
        ] = {}

        for block in document.blocks:
            sheet_index = (
                cls._resolve_sheet_index(
                    block
                )
            )

            sheet_counts[
                sheet_index
            ] = (
                sheet_counts.get(
                    sheet_index,
                    0,
                )
                + 1
            )

        raw_sheets = document.metadata.get(
            "sheets",
            [],
        )

        if isinstance(
            raw_sheets,
            list,
        ):
            updated_sheets: list[
                dict
            ] = []

            logical_page_number = 1

            for record in raw_sheets:
                if not isinstance(
                    record,
                    dict,
                ):
                    continue

                sheet_index = record.get(
                    "sheet_index"
                )

                if sheet_index is None:
                    continue

                sheet_index = int(
                    sheet_index
                )

                if sheet_index not in sheet_counts:
                    continue

                updated = dict(
                    record
                )

                updated[
                    "non_empty_row_count"
                ] = sheet_counts[
                    sheet_index
                ]

                updated[
                    "logical_page_number"
                ] = logical_page_number

                updated[
                    "status"
                ] = "SUCCESS"

                updated_sheets.append(
                    updated
                )

                logical_page_number += 1

            document.metadata[
                "sheets"
            ] = updated_sheets

        document.metadata[
            "block_count"
        ] = len(
            document.blocks
        )

        document.metadata[
            "non_empty_row_count"
        ] = len(
            document.blocks
        )

        document.metadata[
            "processed_sheet_count"
        ] = len(
            sheet_counts
        )

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
                "RowFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "xlsx":
            raise ValueError(
                "RowFilter only accepts XLSX documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )