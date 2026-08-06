from __future__ import annotations

import re

from app.model.document import Document


class TableFilter:
    """
    DOCX 表格文本清洗器。

    约定：
        DOCXLoader 将表格行转换为：

        单元格1 | 单元格2 | 单元格3

    本过滤器负责：
        - 清理表格单元格空白
        - 删除重复单元格
        - 删除全空表格行
        - 统一分隔符格式
        - 删除明显无意义的表格行
        - 保留普通段落原样

    不负责：
        - 章节识别
        - 表格结构建模
        - 合并跨行单元格
        - Chunk
    """

    _SEPARATOR_PATTERN = re.compile(
        r"\s*\|\s*"
    )

    _CONTROL_CHARACTER_PATTERN = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
    )

    _MULTIPLE_SPACES_PATTERN = re.compile(
        r"[ \t]+"
    )

    def __init__(
        self,
        *,
        separator: str = " | ",
        remove_duplicate_cells: bool = True,
        remove_empty_cells: bool = True,
        minimum_non_empty_cells: int = 1,
    ) -> None:

        if not separator:
            raise ValueError(
                "separator cannot be empty."
            )

        if minimum_non_empty_cells < 1:
            raise ValueError(
                "minimum_non_empty_cells must be at least 1."
            )

        self.separator = separator
        self.remove_duplicate_cells = remove_duplicate_cells
        self.remove_empty_cells = remove_empty_cells
        self.minimum_non_empty_cells = minimum_non_empty_cells

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        processed_table_rows = 0
        removed_table_rows = 0
        removed_cells = 0

        for page in document.pages:
            filtered_lines: list[str] = []

            for raw_line in page.text.splitlines():
                line = raw_line.strip()

                if not line:
                    continue

                if not self._looks_like_table_row(
                    line
                ):
                    filtered_lines.append(line)
                    continue

                processed_table_rows += 1

                cells = self._split_cells(
                    line
                )

                normalized_cells: list[str] = []
                previous_cell: str | None = None

                for cell in cells:
                    normalized_cell = self._normalize_cell(
                        cell
                    )

                    if not normalized_cell:
                        if self.remove_empty_cells:
                            removed_cells += 1
                            continue

                    if (
                        self.remove_duplicate_cells
                        and normalized_cell == previous_cell
                    ):
                        removed_cells += 1
                        continue

                    normalized_cells.append(
                        normalized_cell
                    )

                    previous_cell = normalized_cell

                if (
                    len(normalized_cells)
                    < self.minimum_non_empty_cells
                ):
                    removed_table_rows += 1
                    continue

                if self._is_meaningless_row(
                    normalized_cells
                ):
                    removed_table_rows += 1
                    continue

                filtered_lines.append(
                    self.separator.join(
                        normalized_cells
                    )
                )

            page.text = "\n".join(
                filtered_lines
            ).strip()

        document.metadata.update(
            {
                "table_filter": "TableFilter",
                "table_filter_status": "SUCCESS",
                "table_filter_processed_rows": (
                    processed_table_rows
                ),
                "table_filter_removed_rows": (
                    removed_table_rows
                ),
                "table_filter_removed_cells": (
                    removed_cells
                ),
            }
        )

        return document

    @classmethod
    def _looks_like_table_row(
        cls,
        line: str,
    ) -> bool:

        return "|" in line

    @classmethod
    def _split_cells(
        cls,
        line: str,
    ) -> list[str]:

        return cls._SEPARATOR_PATTERN.split(
            line
        )

    @classmethod
    def _normalize_cell(
        cls,
        value: str,
    ) -> str:

        if not value:
            return ""

        normalized = value.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        normalized = cls._CONTROL_CHARACTER_PATTERN.sub(
            "",
            normalized,
        )

        normalized = cls._MULTIPLE_SPACES_PATTERN.sub(
            " ",
            normalized,
        )

        return normalized.strip()

    @staticmethod
    def _is_meaningless_row(
        cells: list[str],
    ) -> bool:
        """
        判断整行是否只有符号、横线等无意义内容。
        """

        if not cells:
            return True

        combined = "".join(cells).strip()

        if not combined:
            return True

        symbol_only_pattern = re.compile(
            r"^[\W_]+$"
        )

        return bool(
            symbol_only_pattern.fullmatch(
                combined
            )
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
                "TableFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "docx":
            raise ValueError(
                "TableFilter only accepts DOCX documents. "
                f"Received file_type: {document.file_type}"
            )