from __future__ import annotations

from app.analyzer.title_detector import (
    TitleDetector,
)
from app.analyzer.title_joiner import (
    TitleJoiner,
)
from app.analyzer.title_normalizer import (
    TitleNormalizer,
)
from app.model.chapter import Chapter
from app.model.content import Content
from app.model.document import Document
from app.model.section import Section


class StructureAnalyzerError(
    RuntimeError
):
    """
    文档结构分析异常。
    """


class StructureAnalyzer:
    """
    编号式 PDF 文档结构分析器。

    数据流：

        Page
          ↓
        TitleNormalizer
          ↓
        TitleJoiner
          ↓
        TitleDetector
          ↓
        Chapter / Section / Content

    负责：

        - 标准化页面文本
        - 合并 PDF 抽取造成的标题断行
        - 检测 Chapter / Section
        - 建立 Chapter、Section、Content
        - 根据 Section ID 修正 Chapter 归属
        - 在缺失 Chapter 标题时建立占位 Chapter
        - 保证正文 Page Number 准确
        - 防止重复 analyze() 累积旧结果

    不负责：

        - PDF 文件读取
        - 页面过滤
        - 页眉页脚删除
        - Section 父子关系
        - Sort Order
        - Chunk
        - Token Count
        - JSON
        - PostgreSQL
    """

    def __init__(
        self,
        *,
        title_detector: TitleDetector | None = None,
        title_normalizer: TitleNormalizer | None = None,
        title_joiner: TitleJoiner | None = None,
    ) -> None:

        self.title_detector = (
            title_detector
            or TitleDetector()
        )

        self.title_normalizer = (
            title_normalizer
            or TitleNormalizer()
        )

        self.title_joiner = (
            title_joiner
            or TitleJoiner()
        )

    # ==================================================
    # Public API
    # ==================================================

    def analyze(
        self,
        document: Document,
    ) -> Document:
        """
        分析 Document.pages 并建立文档结构。

        Args:
            document:
                PDFLoader 生成的 Document。

        Returns:
            已建立 chapters / sections / contents
            的同一个 Document。
        """

        self._validate_document(
            document
        )

        # 保证重复调用 analyze() 时幂等。
        document.chapters.clear()
        document.sections.clear()
        document.contents.clear()

        current_chapter: Chapter | None = None
        current_section: Section | None = None

        chapter_map: dict[
            str,
            Chapter,
        ] = {}

        section_map: dict[
            str,
            Section,
        ] = {}

        content_buffer: list[str] = []

        content_page_number: (
            int | None
        ) = None

        discarded_preamble_count = 0
        synthetic_chapter_count = 0
        detected_heading_count = 0

        def flush_content() -> None:
            """
            将当前正文缓冲区写入 Document。

            Page Number 使用正文开始所在页，
            而不是 flush 时所在页。
            """

            nonlocal content_buffer
            nonlocal content_page_number
            nonlocal discarded_preamble_count

            if not content_buffer:
                content_page_number = None
                return

            text = "\n".join(
                content_buffer
            ).strip()

            content_buffer = []
            page_number = (
                content_page_number
            )
            content_page_number = None

            if not text:
                return

            # 标题前的封面、版权、版本历史等内容
            # 不生成 orphan Content。
            if current_chapter is None:
                discarded_preamble_count += 1
                return

            document.contents.append(
                Content(
                    chapter_id=(
                        current_chapter.id
                    ),
                    section_id=(
                        current_section.id
                        if current_section
                        else None
                    ),
                    text=text,
                    page_number=page_number,
                )
            )

        try:

            for page in document.pages:

                page_number = (
                    page.page_number
                )

                # ======================================
                # 1. Normalize
                # ======================================

                normalized_text = (
                    self.title_normalizer
                    .normalize(
                        page.text
                    )
                )

                if not normalized_text:
                    continue

                lines = (
                    normalized_text
                    .splitlines()
                )

                # ======================================
                # 2. Join Broken Titles
                # ======================================

                lines = (
                    self.title_joiner
                    .join(
                        lines
                    )
                )

                # ======================================
                # 3. Analyze
                # ======================================

                for raw_line in lines:

                    line = (
                        raw_line.strip()
                    )

                    if not line:
                        continue

                    result = (
                        self.title_detector
                        .detect(
                            line
                        )
                    )

                    # ==================================
                    # Normal Content
                    # ==================================

                    if result is None:

                        if (
                            content_page_number
                            is None
                        ):
                            content_page_number = (
                                page_number
                            )

                        content_buffer.append(
                            line
                        )

                        continue

                    detected_heading_count += 1

                    # 标题出现之前先保存正文。
                    flush_content()

                    title_id = str(
                        result["id"]
                    ).strip()

                    title = str(
                        result["title"]
                    ).strip()

                    level = int(
                        result["level"]
                    )

                    if (
                        not title_id
                        or not title
                        or level < 1
                    ):
                        continue

                    # ==================================
                    # Chapter
                    # ==================================

                    if level == 1:

                        chapter = (
                            chapter_map.get(
                                title_id
                            )
                        )

                        if chapter is None:

                            chapter = Chapter(
                                id=title_id,
                                title_jp=title,
                                title_en=None,
                                level=1,
                                page_number=(
                                    page_number
                                ),
                            )

                            document.chapters.append(
                                chapter
                            )

                            chapter_map[
                                title_id
                            ] = chapter

                        else:

                            self._update_title_if_better(
                                existing=chapter,
                                title=title,
                            )

                            # 如果之前是 synthetic Chapter，
                            # 现在遇到了真实 Chapter 标题，
                            # 清除 synthetic 标识。
                            if (
                                chapter.metadata.get(
                                    "synthetic"
                                )
                            ):
                                chapter.metadata.pop(
                                    "synthetic",
                                    None,
                                )

                                chapter.metadata.pop(
                                    "synthetic_reason",
                                    None,
                                )

                                chapter.page_number = (
                                    page_number
                                )

                        current_chapter = (
                            chapter
                        )

                        current_section = (
                            None
                        )

                        continue

                    # ==================================
                    # Section
                    # ==================================

                    chapter_id = (
                        self._resolve_section_chapter_id(
                            section_id=title_id,
                            current_chapter=(
                                current_chapter
                            ),
                        )
                    )

                    if not chapter_id:
                        # TitleDetector 正常产生 level > 1
                        # 时理论上都会存在 Chapter ID。
                        #
                        # 这里属于防御性处理。
                        continue

                    # ==================================
                    # Ensure Chapter
                    # ==================================

                    chapter = (
                        chapter_map.get(
                            chapter_id
                        )
                    )

                    if chapter is None:

                        chapter = (
                            self._create_synthetic_chapter(
                                chapter_id=(
                                    chapter_id
                                ),
                                page_number=(
                                    page_number
                                ),
                            )
                        )

                        document.chapters.append(
                            chapter
                        )

                        chapter_map[
                            chapter_id
                        ] = chapter

                        synthetic_chapter_count += 1

                    # Section ID 比当前上下文更可信。
                    #
                    # 例如：
                    #
                    # current = Chapter 2
                    # heading = 1.4.3
                    #
                    # 应切换到 Chapter 1。
                    current_chapter = (
                        chapter
                    )

                    section = (
                        section_map.get(
                            title_id
                        )
                    )

                    if section is None:

                        section = Section(
                            id=title_id,
                            chapter_id=(
                                chapter_id
                            ),
                            parent_section_id=None,
                            title_jp=title,
                            title_en=None,
                            level=level,
                            page_number=(
                                page_number
                            ),
                        )

                        document.sections.append(
                            section
                        )

                        section_map[
                            title_id
                        ] = section

                    else:

                        # Section ID 推导出的 Chapter
                        # 始终作为最终归属。
                        section.chapter_id = (
                            chapter_id
                        )

                        self._update_title_if_better(
                            existing=section,
                            title=title,
                        )

                        if (
                            section.page_number
                            is None
                        ):
                            section.page_number = (
                                page_number
                            )

                    current_section = (
                        section
                    )

                # ======================================
                # 4. Page Boundary
                # ======================================
                #
                # PDF RAG 中 page_number 是重要 Citation。
                #
                # 不允许正文从 Page 5 一直缓存到 Page 6，
                # 最后全部被标记成 Page 6。
                #
                # 每页末尾 flush，但 Chapter / Section
                # 上下文继续保留到下一页。

                flush_content()

            # 最终防御性 Flush。
            flush_content()

        except StructureAnalyzerError:
            raise

        except Exception as exc:
            raise StructureAnalyzerError(
                "Failed to analyze document "
                f"structure for "
                f"'{document.file_name}': {exc}"
            ) from exc

        # ==============================================
        # Metadata
        # ==============================================

        document.metadata.update(
            {
                "structure_analyzer": (
                    "StructureAnalyzer"
                ),
                "structure_analyzer_status": (
                    "SUCCESS"
                ),
                "detected_heading_count": (
                    detected_heading_count
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
                "synthetic_chapter_count": (
                    synthetic_chapter_count
                ),
                "discarded_preamble_count": (
                    discarded_preamble_count
                ),
            }
        )

        return document

    # ==================================================
    # Chapter Resolution
    # ==================================================

    @staticmethod
    def _resolve_section_chapter_id(
        *,
        section_id: str,
        current_chapter: Chapter | None,
    ) -> str | None:
        """
        推导 Section 所属 Chapter。

        优先级：

            1. section_id 第一段
            2. current_chapter

        Examples:

            1.4.3
                ->
            1

            2.2.1
                ->
            2
        """

        normalized_id = str(
            section_id
            or ""
        ).strip()

        if not normalized_id:
            return (
                current_chapter.id
                if current_chapter
                else None
            )

        if "." in normalized_id:

            chapter_id = (
                normalized_id
                .split(
                    ".",
                    maxsplit=1,
                )[0]
                .strip()
            )

            if chapter_id:
                return chapter_id

        if current_chapter is not None:
            return current_chapter.id

        return None

    # ==================================================
    # Synthetic Chapter
    # ==================================================

    @staticmethod
    def _create_synthetic_chapter(
        *,
        chapter_id: str,
        page_number: int | None,
    ) -> Chapter:
        """
        Section 出现但 Chapter 标题缺失时，
        建立占位 Chapter。

        Example:

            PDF 中只抽取到：

                3.1 User Profile

            但：

                3 User Registration

            因 PDF 提取问题丢失。

        此时建立：

            Chapter 3

        避免 Section 3.1 成为孤立结构。
        """

        return Chapter(
            id=chapter_id,
            title_jp=(
                f"Chapter {chapter_id}"
            ),
            title_en=None,
            level=1,
            page_number=page_number,
            metadata={
                "synthetic": True,
                "synthetic_reason": (
                    "chapter_heading_missing"
                ),
            },
        )

    # ==================================================
    # Title Update
    # ==================================================

    @staticmethod
    def _update_title_if_better(
        *,
        existing: Chapter | Section,
        title: str,
    ) -> None:
        """
        重复标题出现时，
        保留信息量更大的版本。

        当前使用长度作为保守启发式规则。
        """

        normalized_title = str(
            title
            or ""
        ).strip()

        if not normalized_title:
            return

        existing_title = str(
            existing.title_jp
            or ""
        ).strip()

        if (
            not existing_title
            or len(normalized_title)
            > len(existing_title)
        ):
            existing.title_jp = (
                normalized_title
            )

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
                "StructureAnalyzer expects an "
                "app.model.document.Document instance."
            )

        if not str(
            document.file_name
            or ""
        ).strip():
            raise ValueError(
                "Document file_name "
                "cannot be empty."
            )

        if (
            str(
                document.file_type
                or ""
            ).lower()
            != "pdf"
        ):
            raise ValueError(
                "StructureAnalyzer only accepts "
                "PDF documents. "
                f"Received file_type: "
                f"{document.file_type}"
            )

        if not document.pages:
            raise ValueError(
                "PDF document contains "
                "no pages."
            )

        if not any(
            str(
                page.text
                or ""
            ).strip()
            for page
            in document.pages
        ):
            raise ValueError(
                "PDF document contains "
                "no analyzable text."
            )