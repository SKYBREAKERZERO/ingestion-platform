from __future__ import annotations

import re
from collections import Counter

from app.model.document import Document


class HeaderFooterFilter:
    """
    PDF 页眉页脚过滤器。

    处理：
        - 统计顶部/底部多个候选行
        - 删除高频重复页眉页脚
        - 删除动态页码
        - 删除常见公司版权页脚
        - 删除版本号行
        - 保留正文中的普通文本

    示例：
        TOYOTA MOTOR CORPORATION
        v2.51
        41/48
    """

    _PAGE_NUMBER_PATTERNS = (
        re.compile(
            r"^\d+\s*/\s*\d+$"
        ),
        re.compile(
            r"^page\s+\d+(?:\s+of\s+\d+)?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^-\s*\d+\s*-$"
        ),
    )

    _VERSION_PATTERNS = (
        re.compile(
            r"^[vVｖＶ]\s*\d+(?:\.\d+)+$"
        ),
        re.compile(
            r"^(?:ver|version)\.?\s*\d+(?:\.\d+)+$",
            re.IGNORECASE,
        ),
    )

    _STATIC_FOOTER_PATTERNS = (
        re.compile(
            r"^TOYOTA\s+MOTOR\s+CORPORATION$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^DENSO\s+CORPORATION$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^CONFIDENTIAL$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^PROPRIETARY$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^COPYRIGHT\b.*$",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        *,
        header_scan_lines: int = 3,
        footer_scan_lines: int = 5,
        repetition_ratio: float = 0.4,
        minimum_repetition: int = 3,
    ) -> None:

        if header_scan_lines < 1:
            raise ValueError(
                "header_scan_lines must be at least 1."
            )

        if footer_scan_lines < 1:
            raise ValueError(
                "footer_scan_lines must be at least 1."
            )

        if not 0 < repetition_ratio <= 1:
            raise ValueError(
                "repetition_ratio must be between 0 and 1."
            )

        if minimum_repetition < 1:
            raise ValueError(
                "minimum_repetition must be at least 1."
            )

        self.header_scan_lines = header_scan_lines
        self.footer_scan_lines = footer_scan_lines
        self.repetition_ratio = repetition_ratio
        self.minimum_repetition = minimum_repetition

    def filter(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        pages_lines = [
            self._extract_lines(
                page.text
            )
            for page in document.pages
        ]

        if not pages_lines:
            return document

        repeated_headers = self._find_repeated_edge_lines(
            pages_lines=pages_lines,
            edge="header",
            scan_lines=self.header_scan_lines,
        )

        repeated_footers = self._find_repeated_edge_lines(
            pages_lines=pages_lines,
            edge="footer",
            scan_lines=self.footer_scan_lines,
        )

        removed_line_count = 0
        removed_page_number_count = 0
        removed_version_count = 0
        removed_static_footer_count = 0

        for page, lines in zip(
            document.pages,
            pages_lines,
        ):
            filtered_lines: list[str] = []

            for index, line in enumerate(lines):

                normalized = self._normalize_line(
                    line
                )

                if not normalized:
                    continue

                is_header_area = (
                    index < self.header_scan_lines
                )

                is_footer_area = (
                    index
                    >= max(
                        len(lines)
                        - self.footer_scan_lines,
                        0,
                    )
                )

                if (
                    is_header_area
                    and normalized in repeated_headers
                ):
                    removed_line_count += 1
                    continue

                if (
                    is_footer_area
                    and normalized in repeated_footers
                ):
                    removed_line_count += 1
                    continue

                if (
                    is_footer_area
                    and self._is_page_number(
                        normalized
                    )
                ):
                    removed_page_number_count += 1
                    continue

                if (
                    is_footer_area
                    and self._is_version_line(
                        normalized
                    )
                ):
                    removed_version_count += 1
                    continue

                if (
                    is_footer_area
                    and self._is_static_footer(
                        normalized
                    )
                ):
                    removed_static_footer_count += 1
                    continue

                filtered_lines.append(
                    line.strip()
                )

            page.text = "\n".join(
                filtered_lines
            ).strip()

        document.metadata.update(
            {
                "header_footer_filter": (
                    "HeaderFooterFilter"
                ),
                "header_footer_filter_status": (
                    "SUCCESS"
                ),
                "repeated_header_count": len(
                    repeated_headers
                ),
                "repeated_footer_count": len(
                    repeated_footers
                ),
                "removed_repeated_edge_line_count": (
                    removed_line_count
                ),
                "removed_page_number_count": (
                    removed_page_number_count
                ),
                "removed_version_line_count": (
                    removed_version_count
                ),
                "removed_static_footer_count": (
                    removed_static_footer_count
                ),
            }
        )

        return document

    def _find_repeated_edge_lines(
        self,
        *,
        pages_lines: list[list[str]],
        edge: str,
        scan_lines: int,
    ) -> set[str]:

        counter: Counter[str] = Counter()

        for lines in pages_lines:

            if not lines:
                continue

            if edge == "header":
                candidates = lines[
                    :scan_lines
                ]

            elif edge == "footer":
                candidates = lines[
                    -scan_lines:
                ]

            else:
                raise ValueError(
                    f"Unsupported edge: {edge}"
                )

            page_unique_lines = {
                self._normalize_line(line)
                for line in candidates
                if self._normalize_line(line)
            }

            counter.update(
                page_unique_lines
            )

        threshold = max(
            self.minimum_repetition,
            int(
                len(pages_lines)
                * self.repetition_ratio
            ),
        )

        return {
            line
            for line, count in counter.items()
            if count >= threshold
        }

    @staticmethod
    def _extract_lines(
        text: str,
    ) -> list[str]:

        if not text:
            return []

        return [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

    @staticmethod
    def _normalize_line(
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

        return " ".join(
            normalized.split()
        )

    @classmethod
    def _is_page_number(
        cls,
        line: str,
    ) -> bool:

        return any(
            pattern.fullmatch(
                line
            )
            for pattern in cls._PAGE_NUMBER_PATTERNS
        )

    @classmethod
    def _is_version_line(
        cls,
        line: str,
    ) -> bool:

        return any(
            pattern.fullmatch(
                line
            )
            for pattern in cls._VERSION_PATTERNS
        )

    @classmethod
    def _is_static_footer(
        cls,
        line: str,
    ) -> bool:

        return any(
            pattern.fullmatch(
                line
            )
            for pattern in cls._STATIC_FOOTER_PATTERNS
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
                "HeaderFooterFilter expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "pdf":
            raise ValueError(
                "HeaderFooterFilter only accepts PDF documents. "
                f"Received file_type: {document.file_type}"
            )