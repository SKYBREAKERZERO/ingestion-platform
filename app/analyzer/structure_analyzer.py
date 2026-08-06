from __future__ import annotations

from app.model.chapter import Chapter
from app.model.section import Section
from app.model.content import Content

from app.analyzer.title_detector import TitleDetector
from app.analyzer.title_normalizer import TitleNormalizer
from app.analyzer.title_joiner import TitleJoiner


class StructureAnalyzer:
    """
    编号式文档结构分析器。

    负责：
        - 标准化页面文本
        - 合并断行标题
        - 检测 Chapter / Section
        - 建立 Chapter、Section、Content
        - 根据 section_id 修正 Chapter 归属

    不负责：
        - 页面过滤
        - 页眉页脚清理
        - Section 父子关系
        - 排序字段分配
        - Chunk
        - Token 统计
        - JSON / PostgreSQL 保存
    """

    def __init__(self) -> None:

        self.title_detector = TitleDetector()
        self.title_normalizer = TitleNormalizer()
        self.title_joiner = TitleJoiner()

    def analyze(
        self,
        document,
    ):

        current_chapter: Chapter | None = None
        current_section: Section | None = None

        content_buffer: list[str] = []
        current_page: int | None = None

        # =====================
        # Fast Index
        # =====================

        chapter_map: dict[str, Chapter] = {}
        section_map: dict[str, Section] = {}

        def save_content() -> None:
            """
            保存当前正文缓冲区。

            正文会绑定到当前 Chapter 和 Section。
            """

            nonlocal content_buffer

            if not content_buffer:
                return

            text = "\n".join(
                content_buffer
            ).strip()

            content_buffer = []

            if not text:
                return

            document.contents.append(
                Content(
                    chapter_id=(
                        current_chapter.id
                        if current_chapter
                        else None
                    ),
                    section_id=(
                        current_section.id
                        if current_section
                        else None
                    ),
                    text=text,
                    page_number=current_page,
                )
            )

        try:

            for page in document.pages:

                current_page = page.page_number

                # =====================
                # 1. Normalize
                # =====================

                normalized_text = (
                    self.title_normalizer.normalize(
                        page.text
                    )
                )

                lines = normalized_text.splitlines()

                # =====================
                # 2. Join Broken Titles
                # =====================

                lines = self.title_joiner.join(
                    lines
                )

                # =====================
                # 3. Analyze Lines
                # =====================

                for raw_line in lines:

                    line = raw_line.strip()

                    if not line:
                        continue

                    result = self.title_detector.detect(
                        line
                    )

                    # =====================
                    # Normal Content
                    # =====================

                    if result is None:
                        content_buffer.append(
                            line
                        )
                        continue

                    # 标题前的正文先保存
                    save_content()

                    title_id = str(
                        result["id"]
                    ).strip()

                    title = str(
                        result["title"]
                    ).strip()

                    level = int(
                        result["level"]
                    )

                    if not title_id or not title:
                        continue

                    # =====================
                    # Chapter
                    # =====================

                    if level == 1:

                        chapter = chapter_map.get(
                            title_id
                        )

                        if chapter is None:

                            chapter = Chapter(
                                id=title_id,
                                title_jp=title,
                                title_en=None,
                                level=1,
                            )

                            document.chapters.append(
                                chapter
                            )

                            chapter_map[
                                title_id
                            ] = chapter

                        else:

                            existing_title = (
                                chapter.title_jp
                                or ""
                            )

                            # 重复出现时保留信息更完整的标题
                            if len(title) > len(
                                existing_title
                            ):
                                chapter.title_jp = title

                        current_chapter = chapter
                        current_section = None

                        continue

                    # =====================
                    # Section
                    # =====================

                    chapter_id = (
                        self._resolve_section_chapter_id(
                            section_id=title_id,
                            current_chapter=current_chapter,
                        )
                    )

                    # Section 编号优先决定所属 Chapter。
                    #
                    # 示例：
                    # current_chapter = 2
                    # title_id = 1.4.3
                    #
                    # 实际应切回 Chapter 1。
                    if (
                        chapter_id
                        and chapter_id in chapter_map
                    ):
                        current_chapter = chapter_map[
                            chapter_id
                        ]

                    section = section_map.get(
                        title_id
                    )

                    if section is None:

                        section = Section(
                            id=title_id,
                            title_jp=title,
                            title_en=None,
                            level=level,
                            chapter_id=chapter_id,
                        )

                        document.sections.append(
                            section
                        )

                        section_map[
                            title_id
                        ] = section

                    else:

                        # 重复 Section 再次出现时，
                        # 仍强制修正 Chapter 归属。
                        section.chapter_id = chapter_id

                        existing_title = (
                            section.title_jp
                            or ""
                        )

                        if len(title) > len(
                            existing_title
                        ):
                            section.title_jp = title

                    current_section = section

            # =====================
            # 4. Save Last Content
            # =====================

            save_content()

        except Exception as exc:

            raise RuntimeError(
                f"Structure analyze failed: {exc}"
            ) from exc

        return document

    @staticmethod
    def _resolve_section_chapter_id(
        *,
        section_id: str,
        current_chapter: Chapter | None,
    ) -> str | None:
        """
        推导 Section 所属 Chapter。

        优先级：
            1. 从 section_id 第一段推导
            2. 无法推导时使用 current_chapter

        示例：
            1.4.3 -> 1
            2.2.1 -> 2
        """

        normalized_id = str(
            section_id
        ).strip()

        if "." in normalized_id:

            chapter_id = normalized_id.split(
                ".",
                maxsplit=1,
            )[0].strip()

            if chapter_id:
                return chapter_id

        if current_chapter is not None:
            return current_chapter.id

        return None