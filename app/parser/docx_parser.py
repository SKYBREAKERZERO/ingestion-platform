from __future__ import annotations

import re
from collections import defaultdict

from app.analyzer.title_detector import TitleDetector
from app.model.block import BlockType, DocumentBlock
from app.model.chapter import Chapter
from app.model.content import Content
from app.model.document import Document
from app.model.section import Section


class DOCXParser:
    """
    DOCX 结构解析器。

    优先使用 Word Heading 样式建立章节结构。

    当文档没有 Heading 样式时，回退到编号标题识别：

        1 Introduction
        1.1 Purpose
        1.1.1 Connection

    解析结果写入：

        document.chapters
        document.sections
        document.contents
    """

    _NUMBERED_TITLE_PATTERN = re.compile(
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

    _FULLWIDTH_TRANSLATION = str.maketrans(
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

    def __init__(
        self,
        title_detector: TitleDetector | None = None,
    ) -> None:

        self.title_detector = (
            title_detector
            or TitleDetector()
        )

    def parse(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        # 防止同一个 Document 被重复解析时累积数据。
        document.chapters.clear()
        document.sections.clear()
        document.contents.clear()

        if not document.blocks:
            raise ValueError(
                "DOCX document contains no structured blocks. "
                "DOCXLoader must populate document.blocks."
            )

        styled_heading_count = sum(
            1
            for block in document.blocks
            if (
                block.block_type == BlockType.HEADING
                and block.level is not None
            )
        )

        use_style_headings = (
            styled_heading_count > 0
        )

        current_chapter: Chapter | None = None
        current_section: Section | None = None

        chapter_map: dict[str, Chapter] = {}
        section_map: dict[str, Section] = {}

        content_buffer: list[str] = []
        buffer_page_number: int | None = None

        # 无编号标题的自动编号状态。
        generated_counters: defaultdict[int, int] = (
            defaultdict(int)
        )

        removed_invalid_heading_count = 0
        ignored_table_heading_count = 0

        def flush_content() -> None:

            nonlocal content_buffer
            nonlocal buffer_page_number

            if not content_buffer:
                return

            text = "\n".join(
                content_buffer
            ).strip()

            content_buffer = []

            if not text:
                buffer_page_number = None
                return

            # 没有合法 Chapter 的前置内容暂时不写入 Content。
            # 例如封面、改订履历、版权信息。
            if current_chapter is None:
                buffer_page_number = None
                return

            document.contents.append(
                Content(
                    chapter_id=current_chapter.id,
                    section_id=(
                        current_section.id
                        if current_section
                        else None
                    ),
                    text=text,
                    page_number=(
                        buffer_page_number
                        or 1
                    ),
                )
            )

            buffer_page_number = None

        for block in sorted(
            document.blocks,
            key=lambda item: item.order,
        ):
            text = self._normalize_text(
                block.text
            )

            if not text:
                continue

            # 表格行永远作为正文，不参与章节识别。
            if block.block_type == BlockType.TABLE:
                if self._looks_like_numbered_heading(text):
                    ignored_table_heading_count += 1

                if buffer_page_number is None:
                    buffer_page_number = (
                        block.page_number
                        or 1
                    )

                content_buffer.append(text)
                continue

            heading = self._detect_heading(
                block=block,
                use_style_headings=use_style_headings,
                generated_counters=generated_counters,
                current_chapter=current_chapter,
            )

            if heading is None:
                if buffer_page_number is None:
                    buffer_page_number = (
                        block.page_number
                        or 1
                    )

                content_buffer.append(text)
                continue

            flush_content()

            heading_id = heading["id"]
            heading_title = heading["title"]
            heading_level = heading["level"]

            if (
                not heading_id
                or not heading_title
                or heading_level < 1
            ):
                removed_invalid_heading_count += 1
                continue

            # =====================
            # Chapter
            # =====================

            if heading_level == 1:
                chapter = chapter_map.get(
                    heading_id
                )

                if chapter is None:
                    chapter = Chapter(
                        id=heading_id,
                        title_jp=heading_title,
                        title_en=None,
                        level=1,
                    )

                    document.chapters.append(
                        chapter
                    )

                    chapter_map[
                        heading_id
                    ] = chapter

                elif (
                    heading_title
                    and len(heading_title)
                    > len(chapter.title_jp or "")
                ):
                    chapter.title_jp = heading_title

                current_chapter = chapter
                current_section = None
                continue

            # =====================
            # Section
            # =====================

            chapter_id = self._resolve_chapter_id(
                heading_id=heading_id,
                current_chapter=current_chapter,
            )

            # Heading 2/3 出现在任何 Heading 1 之前时，
            # 建立一个合法的占位 Chapter，避免数据库 NULL。
            if chapter_id is None:
                chapter_id = self._generate_fallback_chapter_id(
                    chapter_map
                )

            if chapter_id not in chapter_map:
                fallback_chapter = Chapter(
                    id=chapter_id,
                    title_jp=f"Chapter {chapter_id}",
                    title_en=None,
                    level=1,
                )

                document.chapters.append(
                    fallback_chapter
                )

                chapter_map[
                    chapter_id
                ] = fallback_chapter

            current_chapter = chapter_map[
                chapter_id
            ]

            normalized_section_id = (
                self._ensure_section_id_belongs_to_chapter(
                    section_id=heading_id,
                    chapter_id=chapter_id,
                    level=heading_level,
                    section_map=section_map,
                )
            )

            section = section_map.get(
                normalized_section_id
            )

            if section is None:
                section = Section(
                    id=normalized_section_id,
                    title_jp=heading_title,
                    title_en=None,
                    level=heading_level,
                    chapter_id=chapter_id,
                    parent_section_id=None,
                )

                document.sections.append(
                    section
                )

                section_map[
                    normalized_section_id
                ] = section

            elif (
                heading_title
                and len(heading_title)
                > len(section.title_jp or "")
            ):
                section.title_jp = heading_title

            current_section = section

        flush_content()

        document.metadata.update(
            {
                "parser": "DOCXParser",
                "parser_status": "SUCCESS",
                "docx_heading_strategy": (
                    "word_style"
                    if use_style_headings
                    else "numbered_text_fallback"
                ),
                "styled_heading_count": (
                    styled_heading_count
                ),
                "chapter_count": len(
                    document.chapters
                ),
                "section_count": len(
                    document.sections
                ),
                "content_count": len(
                    document.contents
                ),
                "ignored_table_heading_count": (
                    ignored_table_heading_count
                ),
                "removed_invalid_heading_count": (
                    removed_invalid_heading_count
                ),
            }
        )

        return document

    def _detect_heading(
        self,
        *,
        block: DocumentBlock,
        use_style_headings: bool,
        generated_counters: defaultdict[int, int],
        current_chapter: Chapter | None,
    ) -> dict | None:
        """
        返回统一标题信息：

            {
                "id": "1.2",
                "title": "Purpose",
                "level": 2
            }
        """

        text = self._normalize_text(
            block.text
        )

        if not text:
            return None

        # 表格、图片等不参与标题识别。
        if block.block_type in {
            BlockType.TABLE,
            BlockType.IMAGE,
            BlockType.PAGE_BREAK,
        }:
            return None

        # 优先使用 Word Heading 样式。
        if (
            block.block_type == BlockType.HEADING
            and block.level is not None
        ):
            numbered_result = (
                self._parse_numbered_title(text)
            )

            if numbered_result is not None:
                # Word Heading level 优先于编号计算结果。
                numbered_result["level"] = (
                    block.level
                )

                return numbered_result

            generated_id = self._generate_heading_id(
                level=block.level,
                counters=generated_counters,
                current_chapter=current_chapter,
            )

            return {
                "id": generated_id,
                "title": text,
                "level": block.level,
            }

        # 文档存在 Word Heading 时，
        # 普通段落不再使用宽松正则猜标题。
        if use_style_headings:
            return None

        # 没有 Word Heading 样式时才使用编号回退。
        if block.block_type not in {
            BlockType.PARAGRAPH,
            BlockType.LIST,
            BlockType.TEXTBOX,
        }:
            return None

        direct_result = self._parse_numbered_title(
            text
        )

        if direct_result is not None:
            return direct_result

        # 兼容现有 TitleDetector 的额外规则。
        detector_result = self.title_detector.detect(
            text
        )

        if detector_result is None:
            return None

        return {
            "id": self._normalize_number(
                detector_result["id"]
            ),
            "title": self._normalize_text(
                detector_result["title"]
            ),
            "level": int(
                detector_result["level"]
            ),
        }

    @classmethod
    def _parse_numbered_title(
        cls,
        text: str,
    ) -> dict | None:

        match = cls._NUMBERED_TITLE_PATTERN.match(
            text
        )

        if match is None:
            return None

        heading_id = cls._normalize_number(
            match.group("number")
        )

        title = cls._normalize_text(
            match.group("title")
        )

        if not heading_id or not title:
            return None

        # 页码、版本号、日期等不作为标题。
        if cls._is_invalid_numbered_title(
            heading_id=heading_id,
            title=title,
        ):
            return None

        return {
            "id": heading_id,
            "title": title,
            "level": (
                heading_id.count(".")
                + 1
            ),
        }

    @staticmethod
    def _is_invalid_numbered_title(
        *,
        heading_id: str,
        title: str,
    ) -> bool:

        if "|" in title:
            return True

        if not title.strip():
            return True

        # 常见改订履历日期。
        if re.search(
            r"\b\d{4}/\d{1,2}/\d{1,2}\b",
            title,
        ):
            return True

        # 纯符号标题。
        if re.fullmatch(
            r"[\W_]+",
            title,
        ):
            return True

        # 类似 2 / 48 的页码。
        if re.fullmatch(
            r"\d+\s*/\s*\d+",
            f"{heading_id} {title}",
        ):
            return True

        return False

    @classmethod
    def _generate_heading_id(
        cls,
        *,
        level: int,
        counters: defaultdict[int, int],
        current_chapter: Chapter | None,
    ) -> str:

        # 当前层级递增。
        counters[level] += 1

        # 清除更深层级计数。
        deeper_levels = [
            stored_level
            for stored_level in counters
            if stored_level > level
        ]

        for stored_level in deeper_levels:
            counters.pop(
                stored_level,
                None,
            )

        if level == 1:
            return str(
                counters[1]
            )

        chapter_id = (
            current_chapter.id
            if current_chapter
            else "1"
        )

        parts = [chapter_id]

        for current_level in range(
            2,
            level + 1,
        ):
            value = counters.get(
                current_level,
                1,
            )

            if value <= 0:
                value = 1

            parts.append(
                str(value)
            )

        return ".".join(parts)

    @staticmethod
    def _resolve_chapter_id(
        *,
        heading_id: str,
        current_chapter: Chapter | None,
    ) -> str | None:

        if "." in heading_id:
            return heading_id.split(
                ".",
                maxsplit=1,
            )[0]

        if current_chapter is not None:
            return current_chapter.id

        return None

    @staticmethod
    def _generate_fallback_chapter_id(
        chapter_map: dict[str, Chapter],
    ) -> str:

        index = 1

        while str(index) in chapter_map:
            index += 1

        return str(index)

    @staticmethod
    def _ensure_section_id_belongs_to_chapter(
        *,
        section_id: str,
        chapter_id: str,
        level: int,
        section_map: dict[str, Section],
    ) -> str:

        if (
            section_id.startswith(
                f"{chapter_id}."
            )
            and "." in section_id
        ):
            return section_id

        depth = max(
            level - 1,
            1,
        )

        index = 1

        while True:
            suffix_parts = [
                str(index)
            ]

            if depth > 1:
                suffix_parts.extend(
                    "1"
                    for _ in range(
                        depth - 1
                    )
                )

            candidate = (
                f"{chapter_id}."
                + ".".join(suffix_parts)
            )

            if candidate not in section_map:
                return candidate

            index += 1

    @classmethod
    def _looks_like_numbered_heading(
        cls,
        text: str,
    ) -> bool:

        return (
            cls._NUMBERED_TITLE_PATTERN.match(
                text
            )
            is not None
        )

    @classmethod
    def _normalize_number(
        cls,
        value: str,
    ) -> str:

        return value.translate(
            cls._FULLWIDTH_TRANSLATION
        ).strip(".")

    @staticmethod
    def _normalize_text(
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
                "DOCXParser expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "docx":
            raise ValueError(
                "DOCXParser only accepts DOCX documents. "
                f"Received file_type: {document.file_type}"
            )

        if not document.blocks:
            raise ValueError(
                "DOCX document contains no blocks."
            )

        if not any(
            block.text.strip()
            for block in document.blocks
        ):
            raise ValueError(
                "DOCX document contains no extractable text."
            )