from __future__ import annotations

from collections import defaultdict

from app.model.content import Content
from app.model.document import Document


class Chunker:
    """
    Content 字符长度分块处理器。

    负责：

        - 将超过 max_length 的 Content 拆分
        - 保留原 Chapter / Section / Page 信息
        - 为最终 Content 分配连续 chunk_index
        - 写入 Chunker metadata

    不负责：

        - Token 统计
        - Content 有效性过滤
        - Section 排序
        - JSON / PostgreSQL 保存

    当前 Chunk 策略：

        character-based fixed length

    即：

        max_length=1000

    表示每个 Chunk 最多约 1000 个 Python 字符，
    并不是 1000 Token。
    """

    def __init__(
        self,
        max_length: int = 1000,
    ) -> None:

        if not isinstance(
            max_length,
            int,
        ):
            raise TypeError(
                "max_length must be an integer."
            )

        if max_length <= 0:
            raise ValueError(
                "max_length must be greater than 0."
            )

        self.max_length = max_length

    def process(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        original_content_count = len(
            document.contents
        )

        new_contents: list[Content] = []

        split_content_count = 0
        generated_chunk_count = 0

        # 同一个 Chapter / Section 下的 Chunk
        # 使用连续编号。
        #
        # Example:
        #
        #   section 2.1
        #
        #       Content A
        #           -> 0
        #           -> 1
        #
        #       Content B
        #           -> 2
        #           -> 3
        #
        # 而不是：
        #
        #       Content A
        #           -> 0
        #           -> 1
        #
        #       Content B
        #           -> 0
        #           -> 1
        #
        next_chunk_index: defaultdict[
            tuple[str | None, str | None],
            int,
        ] = defaultdict(int)

        for content in document.contents:

            scope = (
                content.chapter_id,
                content.section_id,
            )

            text = content.text

            # =====================
            # Short Content
            # =====================

            if len(text) <= self.max_length:

                new_content = (
                    content.model_copy()
                )

                new_content.chunk_index = (
                    next_chunk_index[
                        scope
                    ]
                )

                next_chunk_index[
                    scope
                ] += 1

                new_contents.append(
                    new_content
                )

                generated_chunk_count += 1

                continue

            # =====================
            # Long Content
            # =====================

            split_content_count += 1

            for start in range(
                0,
                len(text),
                self.max_length,
            ):

                chunk_text = text[
                    start:
                    start + self.max_length
                ]

                new_content = (
                    content.model_copy()
                )

                new_content.text = (
                    chunk_text
                )

                new_content.chunk_index = (
                    next_chunk_index[
                        scope
                    ]
                )

                next_chunk_index[
                    scope
                ] += 1

                new_contents.append(
                    new_content
                )

                generated_chunk_count += 1

        document.contents = (
            new_contents
        )

        document.metadata.update(
            {
                "chunker": "Chunker",
                "chunker_status": "SUCCESS",
                "chunk_strategy": (
                    "character_fixed_length"
                ),
                "chunk_max_length": (
                    self.max_length
                ),
                "chunk_original_content_count": (
                    original_content_count
                ),
                "chunk_split_content_count": (
                    split_content_count
                ),
                "chunk_final_content_count": len(
                    new_contents
                ),
                "chunk_generated_count": (
                    generated_chunk_count
                ),
            }
        )

        return document

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
                "Chunker expects an "
                "app.model.document.Document instance."
            )