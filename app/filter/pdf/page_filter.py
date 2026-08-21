from __future__ import annotations

import re
import unicodedata

from app.model.document import Document
from app.model.page import Page


class PageFilter:
    """
    PDF 页面过滤器。

    负责：
        - 删除空页面
        - 保守识别并删除目录页
        - 保持原始 page_number 不变
        - 记录页面过滤统计信息

    不负责：
        - 页眉页脚过滤
        - Chapter / Section 解析
        - 标题合并
        - Chunk
        - Token Count

    TOC 判断原则：
        不再使用：

            title_count >= 10

        这种单条件判断。

        而是综合判断：

            - 是否包含 Contents / Table of Contents / 目次 等标记
            - 编号标题行数量
            - 目录式页码引用数量
            - 点线连接符数量
            - 目录候选行占整页比例

        宁可保留可疑页面，
        也不要误删真实正文页。
    """

    # ==================================================
    # Numbered Heading
    # ==================================================

    _NUMBERED_TITLE_PATTERN = re.compile(
        r"""
        ^
        [0-9]+
        (?:
            \.[0-9]+
        )*
        (?:\s+|$)
        """,
        re.VERBOSE,
    )

    # ==================================================
    # TOC Markers
    # ==================================================

    _TOC_HEADING_PATTERNS = (
        re.compile(
            r"^contents?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^table\s+of\s+contents$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^目次$"
        ),
        re.compile(
            r"^目录$"
        ),
        re.compile(
            r"^目録$"
        ),
    )

    # ==================================================
    # TOC Entry
    # ==================================================
    #
    # Examples:
    #
    #   1 Introduction ........ 3
    #   1.2 Purpose ............ 5
    #   Overview ............... 8
    #
    # 注意：
    #   不能只依赖编号，因为很多目录也包含无编号条目。

    _TOC_DOTTED_ENTRY_PATTERN = re.compile(
        r"""
        ^
        .+?
        \s*
        [.…·・]{2,}
        \s*
        \d+
        $
        """,
        re.VERBOSE,
    )

    # ==================================================
    # Trailing Page Reference
    # ==================================================
    #
    # Examples:
    #
    #   1 Introduction 3
    #   1.1 Purpose 15
    #
    # 为避免误判正文，
    # 这里只作为 TOC 辅助信号。

    _TRAILING_PAGE_REFERENCE_PATTERN = re.compile(
        r"""
        ^
        .+?
        \s+
        \d{1,4}
        $
        """,
        re.VERBOSE,
    )

    # ==================================================
    # Page Number Only
    # ==================================================

    _PAGE_NUMBER_PATTERN = re.compile(
        r"^\d+$"
    )

    def __init__(
        self,
        *,
        remove_empty_pages: bool = True,
        remove_toc_pages: bool = True,
        minimum_toc_entries: int = 5,
        toc_entry_ratio: float = 0.45,
    ) -> None:

        if minimum_toc_entries < 1:
            raise ValueError(
                "minimum_toc_entries must be at least 1."
            )

        if not (
            0.0
            < toc_entry_ratio
            <= 1.0
        ):
            raise ValueError(
                "toc_entry_ratio must be "
                "between 0 and 1."
            )

        self.remove_empty_pages = (
            remove_empty_pages
        )

        self.remove_toc_pages = (
            remove_toc_pages
        )

        self.minimum_toc_entries = (
            minimum_toc_entries
        )

        self.toc_entry_ratio = (
            toc_entry_ratio
        )

    # ==================================================
    # Public API
    # ==================================================

    def filter(
        self,
        document: Document,
    ) -> Document:
        """
        过滤 PDF 空页和目录页。

        非 PDF Document 保持旧版兼容行为：
            原样返回。
        """

        self._validate_document(
            document
        )

        # 保留旧行为。
        #
        # PageFilter 属于 PDF Filter，
        # 但避免因为误调用影响其他 Pipeline。
        if (
            str(
                document.file_type
                or ""
            ).lower()
            != "pdf"
        ):
            return document

        retained_pages: list[Page] = []

        removed_empty_count = 0
        removed_toc_count = 0

        original_page_count = len(
            document.pages
        )

        for page in document.pages:

            text = str(
                page.text
                or ""
            ).strip()

            # ==========================================
            # Empty Page
            # ==========================================

            if not text:

                if self.remove_empty_pages:
                    removed_empty_count += 1
                    continue

                retained_pages.append(
                    page
                )
                continue

            lines = self._extract_lines(
                text
            )

            if not lines:

                if self.remove_empty_pages:
                    removed_empty_count += 1
                    continue

                retained_pages.append(
                    page
                )
                continue

            # ==========================================
            # TOC
            # ==========================================

            if (
                self.remove_toc_pages
                and self._looks_like_toc_page(
                    lines
                )
            ):
                removed_toc_count += 1
                continue

            retained_pages.append(
                page
            )

        document.pages = retained_pages

        # ==============================================
        # Metadata
        # ==============================================

        document.metadata.update(
            {
                "page_filter": (
                    "PageFilter"
                ),
                "page_filter_status": (
                    "SUCCESS"
                ),
                "page_filter_original_count": (
                    original_page_count
                ),
                "page_filter_removed_empty": (
                    removed_empty_count
                ),
                "page_filter_removed_toc": (
                    removed_toc_count
                ),
                "page_filter_retained_count": (
                    len(
                        retained_pages
                    )
                ),
            }
        )

        return document

    # ==================================================
    # TOC Detection
    # ==================================================

    def _looks_like_toc_page(
        self,
        lines: list[str],
    ) -> bool:
        """
        判断页面是否很像目录页。

        使用多个信号综合判断，
        避免仅凭标题数量删除正文页。
        """

        if not lines:
            return False

        normalized_lines = [
            self._normalize_line(
                line
            )
            for line in lines
        ]

        normalized_lines = [
            line
            for line in normalized_lines
            if line
        ]

        if not normalized_lines:
            return False

        # ==============================================
        # TOC Heading
        # ==============================================

        has_toc_heading = any(
            self._is_toc_heading(
                line
            )
            for line
            in normalized_lines[:5]
        )

        # ==============================================
        # Signals
        # ==============================================

        numbered_title_count = 0

        dotted_entry_count = 0

        page_reference_count = 0

        toc_candidate_count = 0

        for line in normalized_lines:

            # 单独页码不能算目录项。
            if self._is_page_number_only(
                line
            ):
                continue

            is_numbered = self.is_title(
                line
            )

            is_dotted = (
                self._looks_like_dotted_toc_entry(
                    line
                )
            )

            is_page_reference = (
                self._looks_like_page_reference(
                    line
                )
            )

            if is_numbered:
                numbered_title_count += 1

            if is_dotted:
                dotted_entry_count += 1

            if is_page_reference:
                page_reference_count += 1

            if (
                is_dotted
                or (
                    is_numbered
                    and is_page_reference
                )
            ):
                toc_candidate_count += 1

        line_count = len(
            normalized_lines
        )

        candidate_ratio = (
            toc_candidate_count
            / line_count
            if line_count
            else 0.0
        )

        # ==============================================
        # Strong Case
        # ==============================================
        #
        # 有明确 Contents 标题时，
        # 只需要较少目录项即可确认。

        if has_toc_heading:

            if (
                toc_candidate_count
                >= 3
            ):
                return True

            if (
                dotted_entry_count
                >= 3
            ):
                return True

            if (
                numbered_title_count
                >= self.minimum_toc_entries
                and page_reference_count
                >= 2
            ):
                return True

        # ==============================================
        # No Explicit TOC Heading
        # ==============================================
        #
        # 没有 Contents / 目次 时必须更保守。

        if (
            toc_candidate_count
            < self.minimum_toc_entries
        ):
            return False

        if (
            candidate_ratio
            < self.toc_entry_ratio
        ):
            return False

        # 至少要存在比较明显的页码引用信号。
        if (
            dotted_entry_count < 2
            and page_reference_count < 4
        ):
            return False

        return True

    # ==================================================
    # Public Compatibility API
    # ==================================================

    @classmethod
    def is_title(
        cls,
        line: str,
    ) -> bool:
        """
        判断是否为编号标题形式。

        Examples:

            1 Introduction
            1.2 Purpose
            1.2.3 Detail

        不限制 Section 层级数量。
        """

        normalized = cls._normalize_line(
            line
        )

        if not normalized:
            return False

        return bool(
            cls._NUMBERED_TITLE_PATTERN.match(
                normalized
            )
        )

    # ==================================================
    # TOC Helpers
    # ==================================================

    @classmethod
    def _is_toc_heading(
        cls,
        line: str,
    ) -> bool:

        normalized = cls._normalize_line(
            line
        )

        return any(
            pattern.fullmatch(
                normalized
            )
            is not None
            for pattern
            in cls._TOC_HEADING_PATTERNS
        )

    @classmethod
    def _looks_like_dotted_toc_entry(
        cls,
        line: str,
    ) -> bool:

        normalized = cls._normalize_line(
            line
        )

        return bool(
            cls._TOC_DOTTED_ENTRY_PATTERN.fullmatch(
                normalized
            )
        )

    @classmethod
    def _looks_like_page_reference(
        cls,
        line: str,
    ) -> bool:

        normalized = cls._normalize_line(
            line
        )

        if not normalized:
            return False

        if cls._looks_like_dotted_toc_entry(
            normalized
        ):
            return True

        return bool(
            cls._TRAILING_PAGE_REFERENCE_PATTERN.fullmatch(
                normalized
            )
        )

    @classmethod
    def _is_page_number_only(
        cls,
        line: str,
    ) -> bool:

        normalized = cls._normalize_line(
            line
        )

        return bool(
            cls._PAGE_NUMBER_PATTERN.fullmatch(
                normalized
            )
        )

    # ==================================================
    # Lines
    # ==================================================

    @classmethod
    def _extract_lines(
        cls,
        text: str,
    ) -> list[str]:

        if not text:
            return []

        return [
            normalized
            for raw_line
            in str(
                text
            ).splitlines()
            if (
                normalized := cls._normalize_line(
                    raw_line
                )
            )
        ]

    # ==================================================
    # Normalize
    # ==================================================

    @staticmethod
    def _normalize_line(
        text: str,
    ) -> str:

        if not text:
            return ""

        normalized = unicodedata.normalize(
            "NFKC",
            str(
                text
            ),
        )

        normalized = normalized.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        return " ".join(
            normalized.split()
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
                "PageFilter expects an "
                "app.model.document.Document instance."
            )