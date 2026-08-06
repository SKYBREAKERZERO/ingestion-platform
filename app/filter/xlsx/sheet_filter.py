from __future__ import annotations

import re
from collections.abc import Iterable

from app.model.document import Document


class SheetFilter:
    """
    XLSX Worksheet 过滤器。

    负责：
        - 删除空 Sheet
        - 删除隐藏或 veryHidden Sheet
        - 按 Sheet 名称排除无关工作表
        - 按 Sheet 名称显式保留目标工作表
        - 删除对应的逻辑 Page 和 DocumentBlock
        - 重新分配逻辑页码和 Block 顺序
        - 更新 document.metadata 中的 Sheet 统计信息

    不负责：
        - 删除空行
        - 删除合计行、注释行
        - 表头识别
        - 表格区域识别
        - Chapter / Section 建模
    """

    DEFAULT_EXCLUDED_NAME_PATTERNS = (
        re.compile(
            r"^(?:cover|表紙|封面)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:toc|contents?|目次|目录)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:revision|revision history|change history|"
            r"改訂履歴|改版履歴|変更履歴|变更履历)$",
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
        remove_empty_sheets: bool = True,
        remove_hidden_sheets: bool = True,
        remove_very_hidden_sheets: bool = True,
        exclude_default_names: bool = False,
        include_sheet_names: Iterable[str] | None = None,
        exclude_sheet_names: Iterable[str] | None = None,
        exclude_name_patterns: Iterable[str | re.Pattern[str]]
        | None = None,
        case_sensitive: bool = False,
        minimum_non_empty_rows: int = 1,
        rebuild_pages: bool = True,
        reassign_block_order: bool = True,
    ) -> None:

        if minimum_non_empty_rows < 0:
            raise ValueError(
                "minimum_non_empty_rows cannot be negative."
            )

        self.remove_empty_sheets = remove_empty_sheets
        self.remove_hidden_sheets = remove_hidden_sheets
        self.remove_very_hidden_sheets = (
            remove_very_hidden_sheets
        )

        self.exclude_default_names = (
            exclude_default_names
        )

        self.case_sensitive = case_sensitive

        self.minimum_non_empty_rows = (
            minimum_non_empty_rows
        )

        self.rebuild_pages = rebuild_pages
        self.reassign_block_order = (
            reassign_block_order
        )

        self.include_sheet_names = (
            self._normalize_name_set(
                include_sheet_names
            )
        )

        self.exclude_sheet_names = (
            self._normalize_name_set(
                exclude_sheet_names
            )
        )

        patterns: list[re.Pattern[str]] = []

        if exclude_default_names:
            patterns.extend(
                self.DEFAULT_EXCLUDED_NAME_PATTERNS
            )

        if exclude_name_patterns:
            for pattern in exclude_name_patterns:
                if isinstance(
                    pattern,
                    re.Pattern,
                ):
                    patterns.append(pattern)
                    continue

                flags = (
                    0
                    if case_sensitive
                    else re.IGNORECASE
                )

                patterns.append(
                    re.compile(
                        str(pattern),
                        flags,
                    )
                )

        self.exclude_name_patterns = tuple(
            patterns
        )

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        sheet_records = self._collect_sheet_records(
            document
        )

        retained_sheet_indexes: set[int] = set()
        retained_sheet_names: set[str] = set()

        removed_sheets: list[dict] = []

        for record in sheet_records:
            keep, reason = self._should_keep_sheet(
                record
            )

            sheet_index = record["sheet_index"]
            sheet_name = record["sheet_name"]

            if keep:
                retained_sheet_indexes.add(
                    sheet_index
                )

                retained_sheet_names.add(
                    self._normalize_name(
                        sheet_name
                    )
                )

            else:
                removed_sheets.append(
                    {
                        "sheet_index": sheet_index,
                        "sheet_name": sheet_name,
                        "sheet_state": record[
                            "sheet_state"
                        ],
                        "reason": reason,
                    }
                )

        original_block_count = len(
            document.blocks
        )

        document.blocks = [
            block
            for block in document.blocks
            if self._block_belongs_to_retained_sheet(
                block=block,
                retained_sheet_indexes=(
                    retained_sheet_indexes
                ),
                retained_sheet_names=(
                    retained_sheet_names
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
                retained_sheet_indexes=(
                    retained_sheet_indexes
                ),
            )

        self._update_sheet_metadata(
            document=document,
            retained_sheet_indexes=(
                retained_sheet_indexes
            ),
            removed_sheets=removed_sheets,
        )

        document.metadata.update(
            {
                "sheet_filter": "SheetFilter",
                "sheet_filter_status": "SUCCESS",
                "sheet_filter_original_count": len(
                    sheet_records
                ),
                "sheet_filter_retained_count": len(
                    retained_sheet_indexes
                ),
                "sheet_filter_removed_count": len(
                    removed_sheets
                ),
                "sheet_filter_removed_sheets": (
                    removed_sheets
                ),
                "sheet_filter_removed_block_count": (
                    original_block_count
                    - len(document.blocks)
                ),
            }
        )

        return document

    def _should_keep_sheet(
        self,
        record: dict,
    ) -> tuple[bool, str | None]:

        sheet_name = str(
            record.get(
                "sheet_name",
                "",
            )
        ).strip()

        sheet_state = str(
            record.get(
                "sheet_state",
                "visible",
            )
        ).strip()

        non_empty_row_count = int(
            record.get(
                "non_empty_row_count",
                0,
            )
            or 0
        )

        normalized_name = self._normalize_name(
            sheet_name
        )

        # 显式 include 白名单优先。
        if (
            self.include_sheet_names
            and normalized_name
            not in self.include_sheet_names
        ):
            return False, "not_in_include_list"

        if (
            normalized_name
            in self.exclude_sheet_names
        ):
            return False, "excluded_sheet_name"

        if (
            sheet_state == "hidden"
            and self.remove_hidden_sheets
        ):
            return False, "hidden_sheet"

        if (
            sheet_state == "veryHidden"
            and self.remove_very_hidden_sheets
        ):
            return False, "very_hidden_sheet"

        if (
            self.remove_empty_sheets
            and non_empty_row_count == 0
        ):
            return False, "empty_sheet"

        if (
            non_empty_row_count
            < self.minimum_non_empty_rows
        ):
            return False, "insufficient_non_empty_rows"

        if self._matches_excluded_pattern(
            sheet_name
        ):
            return False, "excluded_name_pattern"

        return True, None

    def _collect_sheet_records(
        self,
        document: Document,
    ) -> list[dict]:

        raw_sheets = document.metadata.get(
            "sheets",
            [],
        )

        records: list[dict] = []

        if isinstance(raw_sheets, list):
            for raw_record in raw_sheets:
                if not isinstance(
                    raw_record,
                    dict,
                ):
                    continue

                if "sheet_index" not in raw_record:
                    continue

                record = dict(
                    raw_record
                )

                record.setdefault(
                    "sheet_name",
                    f"Sheet{record['sheet_index'] + 1}",
                )

                record.setdefault(
                    "sheet_state",
                    "visible",
                )

                record.setdefault(
                    "non_empty_row_count",
                    self._count_sheet_blocks(
                        document=document,
                        sheet_index=int(
                            record["sheet_index"]
                        ),
                    ),
                )

                records.append(record)

        if records:
            return sorted(
                records,
                key=lambda item: int(
                    item["sheet_index"]
                ),
            )

        # metadata 不完整时，从 blocks 回退构建。
        sheet_map: dict[int, dict] = {}

        for block in document.blocks:
            metadata = block.metadata or {}

            sheet_index = metadata.get(
                "sheet_index"
            )

            if sheet_index is None:
                sheet_index = block.table_index

            if sheet_index is None:
                continue

            sheet_index = int(
                sheet_index
            )

            record = sheet_map.setdefault(
                sheet_index,
                {
                    "sheet_index": sheet_index,
                    "sheet_name": metadata.get(
                        "sheet_name",
                        f"Sheet{sheet_index + 1}",
                    ),
                    "sheet_state": metadata.get(
                        "sheet_state",
                        "visible",
                    ),
                    "non_empty_row_count": 0,
                },
            )

            record[
                "non_empty_row_count"
            ] += 1

        return [
            sheet_map[index]
            for index in sorted(sheet_map)
        ]

    @staticmethod
    def _count_sheet_blocks(
        *,
        document: Document,
        sheet_index: int,
    ) -> int:

        count = 0

        for block in document.blocks:
            metadata = block.metadata or {}

            block_sheet_index = metadata.get(
                "sheet_index"
            )

            if block_sheet_index is None:
                block_sheet_index = (
                    block.table_index
                )

            if block_sheet_index is None:
                continue

            if int(
                block_sheet_index
            ) == sheet_index:
                count += 1

        return count

    @staticmethod
    def _block_belongs_to_retained_sheet(
        *,
        block,
        retained_sheet_indexes: set[int],
        retained_sheet_names: set[str],
    ) -> bool:

        metadata = block.metadata or {}

        sheet_index = metadata.get(
            "sheet_index"
        )

        if sheet_index is None:
            sheet_index = block.table_index

        if sheet_index is not None:
            return int(
                sheet_index
            ) in retained_sheet_indexes

        sheet_name = metadata.get(
            "sheet_name"
        )

        if sheet_name is None:
            # 无 Sheet 信息的 Block 默认保留，避免误删。
            return True

        normalized_name = str(
            sheet_name
        ).strip().casefold()

        return (
            normalized_name
            in retained_sheet_names
        )

    @staticmethod
    def _reassign_block_order(
        document: Document,
    ) -> None:

        sorted_blocks = sorted(
            document.blocks,
            key=lambda block: (
                int(
                    block.metadata.get(
                        "sheet_index",
                        block.table_index
                        if block.table_index
                        is not None
                        else 0,
                    )
                ),
                int(
                    block.metadata.get(
                        "row_number",
                        block.row_index
                        if block.row_index
                        is not None
                        else 0,
                    )
                ),
                block.order,
            ),
        )

        for order, block in enumerate(
            sorted_blocks
        ):
            block.order = order

        document.blocks = sorted_blocks

    @staticmethod
    def _rebuild_pages(
        *,
        document: Document,
        retained_sheet_indexes: set[int],
    ) -> None:
        """
        重新按 Sheet 构建逻辑 Page。

        每个保留 Sheet 对应一个 Page。
        """

        blocks_by_sheet: dict[
            int,
            list
        ] = {}

        for block in document.blocks:
            metadata = block.metadata or {}

            sheet_index = metadata.get(
                "sheet_index"
            )

            if sheet_index is None:
                sheet_index = block.table_index

            if sheet_index is None:
                continue

            sheet_index = int(
                sheet_index
            )

            if (
                sheet_index
                not in retained_sheet_indexes
            ):
                continue

            blocks_by_sheet.setdefault(
                sheet_index,
                [],
            ).append(block)

        original_pages = {
            page.page_number: page
            for page in document.pages
        }

        rebuilt_pages = []

        for logical_page_number, sheet_index in enumerate(
            sorted(blocks_by_sheet),
            start=1,
        ):
            sheet_blocks = sorted(
                blocks_by_sheet[sheet_index],
                key=lambda block: (
                    int(
                        block.metadata.get(
                            "row_number",
                            block.row_index
                            if block.row_index
                            is not None
                            else 0,
                        )
                    ),
                    block.order,
                ),
            )

            text = "\n".join(
                block.text.strip()
                for block in sheet_blocks
                if block.text.strip()
            )

            if (
                logical_page_number
                in original_pages
            ):
                page = original_pages[
                    logical_page_number
                ]

                page.page_number = (
                    logical_page_number
                )

                page.text = text

            else:
                from app.model.page import Page

                page = Page(
                    page_number=(
                        logical_page_number
                    ),
                    text=text,
                )

            rebuilt_pages.append(page)

            for block in sheet_blocks:
                block.page_number = (
                    logical_page_number
                )

        document.pages = rebuilt_pages

    @staticmethod
    def _update_sheet_metadata(
        *,
        document: Document,
        retained_sheet_indexes: set[int],
        removed_sheets: list[dict],
    ) -> None:

        raw_sheets = document.metadata.get(
            "sheets",
            [],
        )

        if not isinstance(
            raw_sheets,
            list,
        ):
            raw_sheets = []

        retained_records: list[dict] = []

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

            if (
                sheet_index
                not in retained_sheet_indexes
            ):
                continue

            updated = dict(
                record
            )

            updated[
                "logical_page_number"
            ] = logical_page_number

            updated["status"] = "SUCCESS"

            retained_records.append(
                updated
            )

            logical_page_number += 1

        document.metadata[
            "sheets"
        ] = retained_records

        document.metadata[
            "processed_sheet_count"
        ] = len(retained_records)

        document.metadata[
            "skipped_sheet_count"
        ] = (
            int(
                document.metadata.get(
                    "skipped_sheet_count",
                    0,
                )
                or 0
            )
            + len(removed_sheets)
        )

        document.metadata[
            "block_count"
        ] = len(document.blocks)

        document.metadata[
            "non_empty_row_count"
        ] = len(document.blocks)

    def _matches_excluded_pattern(
        self,
        sheet_name: str,
    ) -> bool:

        return any(
            pattern.search(
                sheet_name
            )
            is not None
            for pattern
            in self.exclude_name_patterns
        )

    def _normalize_name_set(
        self,
        values: Iterable[str] | None,
    ) -> set[str]:

        if values is None:
            return set()

        return {
            self._normalize_name(
                str(value)
            )
            for value in values
            if str(value).strip()
        }

    def _normalize_name(
        self,
        value: str,
    ) -> str:

        normalized = " ".join(
            str(value)
            .replace("\u3000", " ")
            .replace("\xa0", " ")
            .split()
        )

        if self.case_sensitive:
            return normalized

        return normalized.casefold()

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
                "SheetFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "xlsx":
            raise ValueError(
                "SheetFilter only accepts XLSX documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )