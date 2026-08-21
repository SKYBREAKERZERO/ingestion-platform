from __future__ import annotations

import re
from collections.abc import Mapping

from app.model.document import Document


class TitleSentenceCorrector:
    """
    Chapter / Section 标题文本修正器。

    负责：
        - Unicode 标准化后的标题空格修正
        - CamelCase / 粘连单词拆分
        - 标点和括号周围空格规范化
        - 基于可配置词典修正常见错误
        - 同时处理 Chapter 和 Section 标题

    不负责：
        - Heading 合并
        - 标题编号生成
        - Chapter / Section 层级判断
        - 恢复无法可靠推断的大段缺失文本

    设计原则：
        保守修正。只执行确定性较高的文本转换。
    """

    DEFAULT_REPLACEMENTS: dict[str, str] = {
        "AuthorityManagement": "Authority Management",
        "Function Overvieｗ": "Function Overview",
        "Detaile Specification": "Detailed Specification",
        "Car Play": "CarPlay",
        "CenterComm.": "Center Communication",
        "User profile Receive function": (
            "User Profile Receive Function"
        ),
        "User profile Management": (
            "User Profile Management"
        ),
        "User profile Upload/Download": (
            "User Profile Upload/Download"
        ),
        "MM Settings store and load function": (
            "MM Settings Store and Load Function"
        ),
    }

    _MULTIPLE_SPACES_PATTERN = re.compile(
        r"[ \t]+"
    )

    _SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(
        r"\s+([,.;:!?，。；：！？])"
    )

    _SPACE_AFTER_OPENING_BRACKET_PATTERN = re.compile(
        r"([\(\[\{（［｛])\s+"
    )

    _SPACE_BEFORE_CLOSING_BRACKET_PATTERN = re.compile(
        r"\s+([\)\]\}）］｝])"
    )

    _CAMEL_CASE_PATTERN = re.compile(
        r"(?<=[a-z])(?=[A-Z])"
    )

    _LETTER_NUMBER_BOUNDARY_PATTERN = re.compile(
        r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])"
    )

    _SLASH_SPACING_PATTERN = re.compile(
        r"\s*/\s*"
    )

    _HYPHEN_SPACING_PATTERN = re.compile(
        r"\s*-\s*"
    )

    def __init__(
        self,
        *,
        replacements: Mapping[str, str] | None = None,
        enable_default_replacements: bool = True,
        split_camel_case: bool = True,
        split_letter_number: bool = False,
        normalize_title_case: bool = False,
    ) -> None:

        self.split_camel_case = bool(
            split_camel_case
        )

        self.split_letter_number = bool(
            split_letter_number
        )

        self.normalize_title_case = bool(
            normalize_title_case
        )

        merged_replacements: dict[str, str] = {}

        if enable_default_replacements:
            merged_replacements.update(
                self.DEFAULT_REPLACEMENTS
            )

        if replacements:
            merged_replacements.update(
                {
                    str(source): str(target)
                    for source, target
                    in replacements.items()
                }
            )

        # 长字符串优先替换，
        # 避免短规则抢先匹配。
        self.replacements = dict(
            sorted(
                merged_replacements.items(),
                key=lambda item: len(
                    item[0]
                ),
                reverse=True,
            )
        )

    def process(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        corrected_chapter_count = 0
        corrected_section_count = 0
        replacement_count = 0

        # =====================
        # Chapter
        # =====================

        for chapter in document.chapters:
            original_jp = chapter.title_jp
            original_en = chapter.title_en

            corrected_jp, jp_replacements = (
                self.correct_title(
                    original_jp or ""
                )
            )

            corrected_en, en_replacements = (
                self.correct_title(
                    original_en or ""
                )
            )

            chapter.title_jp = (
                corrected_jp
                or None
            )

            chapter.title_en = (
                corrected_en
                or None
            )

            replacement_count += (
                jp_replacements
                + en_replacements
            )

            if (
                chapter.title_jp
                != original_jp
                or chapter.title_en
                != original_en
            ):
                corrected_chapter_count += 1

        # =====================
        # Section
        # =====================

        for section in document.sections:
            original_jp = section.title_jp
            original_en = section.title_en

            corrected_jp, jp_replacements = (
                self.correct_title(
                    original_jp or ""
                )
            )

            corrected_en, en_replacements = (
                self.correct_title(
                    original_en or ""
                )
            )

            section.title_jp = (
                corrected_jp
                or None
            )

            section.title_en = (
                corrected_en
                or None
            )

            replacement_count += (
                jp_replacements
                + en_replacements
            )

            if (
                section.title_jp
                != original_jp
                or section.title_en
                != original_en
            ):
                corrected_section_count += 1

        # =====================
        # Metadata
        # =====================

        document.metadata.update(
            {
                "title_sentence_corrector": (
                    "TitleSentenceCorrector"
                ),
                "title_sentence_corrector_status": (
                    "SUCCESS"
                ),
                "corrected_chapter_count": (
                    corrected_chapter_count
                ),
                "corrected_section_count": (
                    corrected_section_count
                ),
                "title_replacement_count": (
                    replacement_count
                ),
                "title_split_camel_case": (
                    self.split_camel_case
                ),
                "title_split_letter_number": (
                    self.split_letter_number
                ),
                "title_normalize_title_case": (
                    self.normalize_title_case
                ),
            }
        )

        return document

    def correct_title(
        self,
        text: str,
    ) -> tuple[str, int]:
        """
        修正单个标题。

        Returns:
            corrected_text
            replacement_count
        """

        if not text:
            return "", 0

        if not isinstance(
            text,
            str,
        ):
            raise TypeError(
                "TitleSentenceCorrector.correct_title() "
                "expects text to be a string."
            )

        corrected = self._normalize_spacing(
            text
        )

        # =====================
        # Explicit Replacement
        # =====================
        #
        # 显式词典优先执行一次。
        #
        # Example:
        #
        #     Car Play
        #         ↓
        #     CarPlay

        corrected, replacement_count = (
            self._apply_replacements(
                corrected,
                count_replacements=True,
            )
        )

        # =====================
        # CamelCase
        # =====================

        if self.split_camel_case:
            corrected = self._split_camel_case(
                corrected,
                split_letter_number=(
                    self.split_letter_number
                ),
            )

        corrected = self._normalize_spacing(
            corrected
        )

        # =====================
        # Title Case
        # =====================

        if self.normalize_title_case:
            corrected = (
                self._apply_safe_title_case(
                    corrected
                )
            )

        # =====================
        # Final Replacement
        # =====================
        #
        # 显式 replacement 必须具有
        # 最终最高优先级。
        #
        # 否则：
        #
        #     Car Play
        #       ↓ replacement
        #     CarPlay
        #       ↓ camel split
        #     Car Play
        #
        # 前面的修正会被撤销。
        #
        # 第二次 replacement 不增加统计数量，
        # 仅用于稳定最终结果。

        corrected, _ = (
            self._apply_replacements(
                corrected,
                count_replacements=False,
            )
        )

        corrected = self._normalize_spacing(
            corrected
        )

        return (
            corrected,
            replacement_count,
        )

    def _apply_replacements(
        self,
        text: str,
        *,
        count_replacements: bool,
    ) -> tuple[str, int]:
        """
        应用显式 replacement。

        规则已经在 __init__ 中按 source
        长度从长到短排列。

        Args:
            text:
                输入文本。

            count_replacements:
                是否统计 replacement 次数。

        Returns:
            corrected_text
            replacement_count
        """

        corrected = text
        replacement_count = 0

        for source, target in (
            self.replacements.items()
        ):
            if source not in corrected:
                continue

            occurrences = corrected.count(
                source
            )

            corrected = corrected.replace(
                source,
                target,
            )

            if count_replacements:
                replacement_count += (
                    occurrences
                )

        return (
            corrected,
            replacement_count,
        )

    @classmethod
    def _normalize_spacing(
        cls,
        text: str,
    ) -> str:
        """
        标题空格和标点规范化。
        """

        normalized = text.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        normalized = (
            cls._MULTIPLE_SPACES_PATTERN.sub(
                " ",
                normalized,
            )
        )

        normalized = (
            cls._SPACE_BEFORE_PUNCTUATION_PATTERN.sub(
                r"\1",
                normalized,
            )
        )

        normalized = (
            cls._SPACE_AFTER_OPENING_BRACKET_PATTERN.sub(
                r"\1",
                normalized,
            )
        )

        normalized = (
            cls._SPACE_BEFORE_CLOSING_BRACKET_PATTERN.sub(
                r"\1",
                normalized,
            )
        )

        normalized = (
            cls._SLASH_SPACING_PATTERN.sub(
                "/",
                normalized,
            )
        )

        normalized = (
            cls._HYPHEN_SPACING_PATTERN.sub(
                "-",
                normalized,
            )
        )

        return normalized.strip()

    @classmethod
    def _split_camel_case(
        cls,
        text: str,
        *,
        split_letter_number: bool = False,
    ) -> str:
        """
        拆分普通 CamelCase。

        Example:

            AuthorityManagement
                ->
            Authority Management

        默认不会拆分：

            MM21
            21MM
            CAN1
            ECU2

        因为这些通常是技术标识符。
        """

        corrected = (
            cls._CAMEL_CASE_PATTERN.sub(
                " ",
                text,
            )
        )

        if split_letter_number:
            corrected = (
                cls._LETTER_NUMBER_BOUNDARY_PATTERN.sub(
                    " ",
                    corrected,
                )
            )

        return corrected

    @staticmethod
    def _apply_safe_title_case(
        text: str,
    ) -> str:
        """
        仅对纯英文标题执行有限 Title Case。

        缩写、日文、中英文混合标题保持原样。
        """

        if not re.fullmatch(
            r"[A-Za-z0-9 /&()_\-.,:]+",
            text,
        ):
            return text

        lower_words = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "of",
            "on",
            "or",
            "the",
            "to",
            "with",
        }

        words = text.split()

        result: list[str] = []

        for index, word in enumerate(
            words
        ):
            # 短大写缩写保持原样。
            #
            # Example:
            #
            #     ECU
            #     CAN
            #     API
            #     HMI

            if (
                word.isupper()
                and len(word) <= 6
            ):
                result.append(
                    word
                )

                continue

            lower_word = word.lower()

            # 非首词的小词保持小写。
            if (
                index > 0
                and lower_word
                in lower_words
            ):
                result.append(
                    lower_word
                )

                continue

            result.append(
                lower_word[:1].upper()
                + lower_word[1:]
            )

        return " ".join(
            result
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
                "TitleSentenceCorrector expects an "
                "app.model.document.Document instance."
            )