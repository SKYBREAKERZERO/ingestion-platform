from __future__ import annotations

from app.model.document import Document
from app.model.section import Section


class SectionHierarchyBuilder:
    """
    Section 层级关系构建器。

    根据 Section ID 建立：

        parent_section_id

    示例：

        1.2
        1.2.3
        1.2.3.4

    得到：

        1.2
            parent = None

        1.2.3
            parent = 1.2

        1.2.3.4
            parent = 1.2.3

    如果直接父节点不存在：

        1.2
        1.2.3.4

    则寻找最近的现存祖先：

        1.2.3.4
            parent = 1.2

    不负责：

        - 创建缺失 Section
        - 修改 Section ID
        - 修改 Chapter ID
        - 修改 Section level
        - Section 排序
    """

    def process(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        # =====================
        # 建立 Section 索引
        # =====================

        section_map: dict[
            str,
            Section,
        ] = {
            section.id: section
            for section in document.sections
        }

        assigned_parent_count = 0
        root_section_count = 0
        fallback_parent_count = 0

        # =====================
        # 设置父节点
        # =====================

        for section in document.sections:

            immediate_parent_id = (
                self.find_parent(
                    section.id
                )
            )

            parent_id = (
                self._find_existing_parent(
                    section=section,
                    section_map=section_map,
                )
            )

            if parent_id is None:
                section.parent_section_id = None
                root_section_count += 1
                continue

            section.parent_section_id = (
                parent_id
            )

            assigned_parent_count += 1

            if (
                immediate_parent_id is not None
                and parent_id
                != immediate_parent_id
            ):
                fallback_parent_count += 1

        # =====================
        # Metadata
        # =====================

        document.metadata.update(
            {
                "section_hierarchy_builder": (
                    "SectionHierarchyBuilder"
                ),
                "section_hierarchy_status": (
                    "SUCCESS"
                ),
                "section_hierarchy_section_count": len(
                    document.sections
                ),
                "section_hierarchy_parent_count": (
                    assigned_parent_count
                ),
                "section_hierarchy_root_count": (
                    root_section_count
                ),
                "section_hierarchy_fallback_parent_count": (
                    fallback_parent_count
                ),
            }
        )

        return document

    def _find_existing_parent(
        self,
        *,
        section: Section,
        section_map: dict[str, Section],
    ) -> str | None:
        """
        从直接父节点开始向上寻找最近的现存祖先。

        同时要求：

            - parent 不能等于自己
            - 如果双方都有 chapter_id，
              必须属于同一个 Chapter
        """

        candidate_id = self.find_parent(
            section.id
        )

        while candidate_id is not None:

            if candidate_id == section.id:
                return None

            candidate = section_map.get(
                candidate_id
            )

            if candidate is not None:

                if self._same_chapter(
                    section,
                    candidate,
                ):
                    return candidate.id

            candidate_id = self.find_parent(
                candidate_id
            )

        return None

    @staticmethod
    def _same_chapter(
        section: Section,
        parent: Section,
    ) -> bool:
        """
        防止 malformed Section ID 导致跨 Chapter 挂载。

        如果其中一方暂时没有 chapter_id，
        不在这里拒绝，由其他结构处理器负责补全。
        """

        if (
            section.chapter_id is None
            or parent.chapter_id is None
        ):
            return True

        return (
            section.chapter_id
            == parent.chapter_id
        )

    @staticmethod
    def find_parent(
        section_id: str,
    ) -> str | None:
        """
        根据 Section ID 返回直接父级 ID。

        Examples:

            1
                -> None

            1.2
                -> 1

            1.2.3
                -> 1.2

            1.2.3.4
                -> 1.2.3

        注意：

            返回的是语法上的直接父 ID。

            该 ID 是否真实存在，
            由 process() 负责判断。
        """

        if section_id is None:
            return None

        normalized_id = str(
            section_id
        ).strip().strip(".")

        if not normalized_id:
            return None

        parts = [
            part.strip()
            for part in normalized_id.split(".")
            if part.strip()
        ]

        # 只有一级时没有 Section parent。
        #
        # 对于：
        #
        #     1.2
        #
        # find_parent() 会返回：
        #
        #     1
        #
        # 但因为 Chapter "1" 通常不在 section_map，
        # process() 最终仍会设置 parent_section_id=None。
        if len(parts) <= 1:
            return None

        return ".".join(
            parts[:-1]
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
                "SectionHierarchyBuilder expects an "
                "app.model.document.Document instance."
            )