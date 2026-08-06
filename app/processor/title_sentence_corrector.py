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
        normalize_title_case: bool = False,
    ) -> None:

        self.split_camel_case = split_camel_case
        self.normalize_title_case = normalize_title_case

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

        # 长字符串优先替换，避免短规则抢先匹配。
        self.replacements = dict(
            sorted(
                merged_replacements.items(),
                key=lambda item: len(item[0]),
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

        for chapter in document.chapters:
            original_jp = chapter.title_jp
            original_en = getattr(
                chapter,
                "title_en",
                None,
            )

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
                corrected_jp or None
            )

            chapter.title_en = (
                corrected_en or None
            )

            replacement_count += (
                jp_replacements
                + en_replacements
            )

            if (
                chapter.title_jp != original_jp
                or chapter.title_en != original_en
            ):
                corrected_chapter_count += 1

        for section in document.sections:
            original_jp = section.title_jp
            original_en = getattr(
                section,
                "title_en",
                None,
            )

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
                corrected_jp or None
            )

            section.title_en = (
                corrected_en or None
            )

            replacement_count += (
                jp_replacements
                + en_replacements
            )

            if (
                section.title_jp != original_jp
                or section.title_en != original_en
            ):
                corrected_section_count += 1

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
            }
        )

        return document

    def correct_title(
        self,
        text: str,
    ) -> tuple[str, int]:

        if not text:
            return "", 0

        corrected = self._normalize_spacing(
            text
        )

        replacement_count = 0

        for source, target in self.replacements.items():
            if source not in corrected:
                continue

            occurrences = corrected.count(
                source
            )

            corrected = corrected.replace(
                source,
                target,
            )

            replacement_count += occurrences

        if self.split_camel_case:
            corrected = self._split_camel_case(
                corrected
            )

        corrected = self._normalize_spacing(
            corrected
        )

        if self.normalize_title_case:
            corrected = self._apply_safe_title_case(
                corrected
            )

        return corrected, replacement_count

    @classmethod
    def _normalize_spacing(
        cls,
        text: str,
    ) -> str:

        normalized = text.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        normalized = cls._MULTIPLE_SPACES_PATTERN.sub(
            " ",
            normalized,
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

        normalized = cls._SLASH_SPACING_PATTERN.sub(
            "/",
            normalized,
        )

        normalized = cls._HYPHEN_SPACING_PATTERN.sub(
            "-",
            normalized,
        )

        return normalized.strip()

    @classmethod
    def _split_camel_case(
        cls,
        text: str,
    ) -> str:

        corrected = cls._CAMEL_CASE_PATTERN.sub(
            " ",
            text,
        )

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

        for index, word in enumerate(words):
            if (
                word.isupper()
                and len(word) <= 6
            ):
                result.append(word)
                continue

            lower_word = word.lower()

            if (
                index > 0
                and lower_word in lower_words
            ):
                result.append(lower_word)
                continue

            result.append(
                lower_word[:1].upper()
                + lower_word[1:]
            )

        return " ".join(result)

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