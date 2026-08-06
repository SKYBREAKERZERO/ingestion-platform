from __future__ import annotations

import re
import unicodedata


class TitleDetector:
    """
    编号式标题检测器。

    支持：
        1 Introduction
        1.1 Purpose
        1.1.1 Detail Specification

    排除：
        2/48
        2018.12.20 Revision history
        2.9 Refer to 2.9 Now Playing
        带明显正文语义的长句
        表格行
    """

    _TITLE_PATTERN = re.compile(
        r"""
        ^
        (?P<number>
            [0-9０-９]+
            (?:
                [\.．]
                [0-9０-９]+
            )*
        )
        [\s　]+
        (?P<title>.+?)
        $
        """,
        re.VERBOSE,
    )

    _PAGE_NUMBER_PATTERNS = (
        re.compile(r"^\d+\s*/\s*\d+$"),
        re.compile(r"^page\s+\d+$", re.IGNORECASE),
        re.compile(r"^-\s*\d+\s*-$"),
    )

    _DATE_ID_PATTERN = re.compile(
        r"^(?:19|20)\d{2}\.\d{1,2}\.\d{1,2}$"
    )

    _INVALID_TITLE_MARKERS = (
        "参照",
        "refer to",
        "see section",
        "see chapter",
        "以下",
        "に伴い",
        "場合",
        "とする",
        "ものとする",
        "shall",
        "must",
        "should",
        "is defined",
        "are defined",
        "according to",
    )

    _SENTENCE_ENDINGS = (
        "。",
        "！",
        "？",
        ".",
        "!",
        "?",
        "です",
        "ます",
        "した",
        "する",
    )

    _NUMBER_TRANSLATION = str.maketrans(
        {
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "．": ".",
        }
    )

    @classmethod
    def detect(
        cls,
        text: str,
    ) -> dict[str, str | int] | None:

        normalized_text = cls._normalize_text(
            text
        )

        if not normalized_text:
            return None

        if cls._is_page_number(
            normalized_text
        ):
            return None

        if "|" in normalized_text:
            return None

        match = cls._TITLE_PATTERN.match(
            normalized_text
        )

        if match is None:
            return None

        raw_id = match.group(
            "number"
        )

        title = cls._normalize_text(
            match.group("title")
        )

        chapter_id = cls.normalize_number(
            raw_id
        )

        if not chapter_id or not title:
            return None

        if cls._DATE_ID_PATTERN.fullmatch(
            chapter_id
        ):
            return None

        if len(title) < 2:
            return None

        if len(title) > 120:
            return None

        if re.fullmatch(
            r"[\W_]+",
            title,
        ):
            return None

        if cls._contains_invalid_marker(
            title
        ):
            return None

        if cls._looks_like_body_sentence(
            title
        ):
            return None

        level = (
            chapter_id.count(".")
            + 1
        )

        return {
            "id": chapter_id,
            "title": title,
            "level": level,
        }

    @classmethod
    def normalize_number(
        cls,
        value: str,
    ) -> str:

        normalized = unicodedata.normalize(
            "NFKC",
            value,
        )

        normalized = normalized.translate(
            cls._NUMBER_TRANSLATION
        )

        normalized = re.sub(
            r"\s*\.\s*",
            ".",
            normalized,
        )

        return normalized.strip(".")

    @classmethod
    def _normalize_text(
        cls,
        text: str,
    ) -> str:

        if not text:
            return ""

        normalized = unicodedata.normalize(
            "NFKC",
            text,
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

        return " ".join(
            normalized.split()
        )

    @classmethod
    def _is_page_number(
        cls,
        text: str,
    ) -> bool:

        return any(
            pattern.fullmatch(
                text
            )
            for pattern
            in cls._PAGE_NUMBER_PATTERNS
        )

    @classmethod
    def _contains_invalid_marker(
        cls,
        title: str,
    ) -> bool:

        lower_title = title.lower()

        return any(
            marker.lower()
            in lower_title
            for marker
            in cls._INVALID_TITLE_MARKERS
        )

    @classmethod
    def _looks_like_body_sentence(
        cls,
        title: str,
    ) -> bool:

        if title.endswith(
            cls._SENTENCE_ENDINGS
        ):
            return True

        punctuation_count = sum(
            title.count(mark)
            for mark in (
                ",",
                "，",
                ";",
                "；",
            )
        )

        if punctuation_count >= 2:
            return True

        if len(title) > 80:
            return True

        return False