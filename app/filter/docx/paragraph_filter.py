from __future__ import annotations

import re

from app.model.document import Document


class ParagraphFilter:
    """
    DOCX 段落清洗器。

    负责：
        - 清理空白字符
        - 删除不可见控制字符
        - 合并同一行中的重复空格
        - 删除连续重复行
        - 删除纯页码行
        - 保留标题、正文、表格文本的原始顺序

    不负责：
        - 章节识别
        - 标题合并
        - 表格解析
        - Chunk
    """

    _PAGE_NUMBER_PATTERNS = (
        re.compile(r"^\d+$"),
        re.compile(r"^\d+\s*/\s*\d+$"),
        re.compile(r"^page\s+\d+$", re.IGNORECASE),
        re.compile(r"^-\s*\d+\s*-$"),
    )

    _CONTROL_CHARACTER_PATTERN = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
    )

    _MULTIPLE_SPACES_PATTERN = re.compile(
        r"[ \t]+"
    )

    _MULTIPLE_BLANK_LINES_PATTERN = re.compile(
        r"\n{3,}"
    )

    def __init__(
        self,
        *,
        remove_page_numbers: bool = True,
        remove_duplicate_lines: bool = True,
        minimum_line_length: int = 1,
    ) -> None:

        if minimum_line_length < 0:
            raise ValueError(
                "minimum_line_length cannot be negative."
            )

        self.remove_page_numbers = remove_page_numbers
        self.remove_duplicate_lines = remove_duplicate_lines
        self.minimum_line_length = minimum_line_length

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        removed_empty_count = 0
        removed_page_number_count = 0
        removed_duplicate_count = 0

        for page in document.pages:
            source_lines = page.text.splitlines()

            filtered_lines: list[str] = []
            previous_line: str | None = None

            for raw_line in source_lines:
                line = self._normalize_line(
                    raw_line
                )

                if not line:
                    removed_empty_count += 1
                    continue

                if len(line) < self.minimum_line_length:
                    removed_empty_count += 1
                    continue

                if (
                    self.remove_page_numbers
                    and self._is_page_number(line)
                ):
                    removed_page_number_count += 1
                    continue

                if (
                    self.remove_duplicate_lines
                    and previous_line == line
                ):
                    removed_duplicate_count += 1
                    continue

                filtered_lines.append(line)
                previous_line = line

            page.text = "\n".join(
                filtered_lines
            ).strip()

        document.metadata.update(
            {
                "paragraph_filter": "ParagraphFilter",
                "paragraph_filter_status": "SUCCESS",
                "paragraph_filter_removed_empty": (
                    removed_empty_count
                ),
                "paragraph_filter_removed_page_numbers": (
                    removed_page_number_count
                ),
                "paragraph_filter_removed_duplicates": (
                    removed_duplicate_count
                ),
            }
        )

        return document

    @classmethod
    def _normalize_line(
        cls,
        text: str,
    ) -> str:

        if not text:
            return ""

        normalized = text.replace(
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

    @classmethod
    def _is_page_number(
        cls,
        line: str,
    ) -> bool:

        return any(
            pattern.fullmatch(line)
            for pattern in cls._PAGE_NUMBER_PATTERNS
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
                "ParagraphFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "docx":
            raise ValueError(
                "ParagraphFilter only accepts DOCX documents. "
                f"Received file_type: {document.file_type}"
            )