from __future__ import annotations

from app.model.document import Document


class ContentFilter:
    """
    正文过滤器。

    保留：
        - Section 级正文
        - Chapter 级正文

    删除：
        - 没有 Chapter 和 Section 归属的孤立正文
        - 空正文
        - 仅包含空白字符的正文
    """

    def filter(
        self,
        document: Document,
    ) -> Document:

        filtered_contents = []

        removed_empty_count = 0
        removed_orphan_count = 0

        for content in document.contents:

            # =====================
            # Normalize Text
            # =====================

            text = str(
                content.text
                or ""
            ).strip()

            # =====================
            # Remove Empty Content
            # =====================

            if not text:
                removed_empty_count += 1
                continue

            # =====================
            # Remove Orphan Content
            # =====================
            #
            # 允许：
            #   chapter_id 有值、section_id=None
            #   -> Chapter 级正文
            #
            # 允许：
            #   section_id 有值
            #   -> Section 级正文
            #
            # 删除：
            #   chapter_id=None 且 section_id=None

            if (
                not content.chapter_id
                and not content.section_id
            ):
                removed_orphan_count += 1
                continue

            content.text = text

            filtered_contents.append(
                content
            )

        document.contents = filtered_contents

        document.metadata.update(
            {
                "content_filter": "ContentFilter",
                "content_filter_status": "SUCCESS",
                "content_filter_removed_empty": (
                    removed_empty_count
                ),
                "content_filter_removed_orphan": (
                    removed_orphan_count
                ),
                "content_filter_retained_count": len(
                    filtered_contents
                ),
            }
        )

        return document