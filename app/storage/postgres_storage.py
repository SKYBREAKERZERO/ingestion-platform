from __future__ import annotations

from typing import Any

from app.database.connection import DatabaseConnection
from app.model.document import Document


class PostgresStorageError(RuntimeError):
    """PostgreSQL 存储层异常。"""


class PostgresStorage:
    """
    Document PostgreSQL 存储实现。

    保存顺序：

        documents
        → chapters
        → sections
        → contents

    特性：

        - 单事务保存
        - Document / Chapter / Section 使用 UPSERT
        - 每次重新导入时替换旧 Contents
        - 自动删除当前文档中已经不存在的 Chapter / Section
        - 防止 chapter_id=None 的孤立 Section 入库
        - 防止生成 None.ROOT
        - 内容变更后 embedding_status 重置为 PENDING
    """

    def __init__(
        self,
        database_connection: DatabaseConnection | None = None,
    ) -> None:

        self.db = (
            database_connection
            or DatabaseConnection()
        )

    def save(
        self,
        document: Document,
    ) -> bool:

        self._validate_document(
            document
        )

        document_id = self._resolve_document_id(
            document
        )

        try:
            with self.db.connect() as conn:
                try:
                    with conn.cursor() as cur:

                        # ==========================
                        # 1. Document
                        # ==========================

                        self._save_document(
                            cur=cur,
                            document=document,
                            document_id=document_id,
                        )

                        # ==========================
                        # 2. Chapters
                        # ==========================

                        chapter_ids = self._save_chapters(
                            cur=cur,
                            document=document,
                            document_id=document_id,
                        )

                        # ==========================
                        # 3. Sections
                        # ==========================

                        section_ids = self._save_sections(
                            cur=cur,
                            document=document,
                            document_id=document_id,
                            chapter_ids=chapter_ids,
                        )

                        # ==========================
                        # 4. Remove stale structure
                        # ==========================

                        self._delete_stale_sections(
                            cur=cur,
                            document_id=document_id,
                            section_ids=section_ids,
                        )

                        self._delete_stale_chapters(
                            cur=cur,
                            document_id=document_id,
                            chapter_ids=chapter_ids,
                        )

                        # ==========================
                        # 5. Contents
                        # ==========================

                        self._replace_contents(
                            cur=cur,
                            document=document,
                            document_id=document_id,
                            chapter_ids=chapter_ids,
                            section_ids=section_ids,
                        )

                    conn.commit()

                except Exception:
                    conn.rollback()
                    raise

        except Exception as exc:
            raise PostgresStorageError(
                f"Failed to save document "
                f"'{document.file_name}' to PostgreSQL: {exc}"
            ) from exc

        return True

    # ==================================================
    # Document
    # ==================================================

    @staticmethod
    def _save_document(
        *,
        cur,
        document: Document,
        document_id: str,
    ) -> None:

        cur.execute(
            """
            INSERT INTO documents
            (
                document_id,
                title,
                module
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
            ON CONFLICT
            (
                document_id
            )
            DO UPDATE SET
                title = EXCLUDED.title,
                module = EXCLUDED.module
            """,
            (
                document_id,
                document.file_name,
                document.file_type,
            ),
        )

    # ==================================================
    # Chapters
    # ==================================================

    @staticmethod
    def _save_chapters(
        *,
        cur,
        document: Document,
        document_id: str,
    ) -> set[str]:

        chapter_ids: set[str] = set()

        for fallback_order, chapter in enumerate(
            document.chapters,
            start=1,
        ):
            chapter_id = str(
                chapter.id
            ).strip()

            if not chapter_id:
                continue

            if chapter_id in chapter_ids:
                continue

            chapter_ids.add(
                chapter_id
            )

            sort_order = getattr(
                chapter,
                "sort_order",
                None,
            )

            if sort_order is None:
                sort_order = fallback_order

            cur.execute(
                """
                INSERT INTO chapters
                (
                    document_id,
                    chapter_id,
                    title_jp,
                    title_en,
                    sort_order
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                ON CONFLICT
                (
                    document_id,
                    chapter_id
                )
                DO UPDATE SET
                    title_jp = EXCLUDED.title_jp,
                    title_en = EXCLUDED.title_en,
                    sort_order = EXCLUDED.sort_order
                """,
                (
                    document_id,
                    chapter_id,
                    getattr(
                        chapter,
                        "title_jp",
                        None,
                    ),
                    getattr(
                        chapter,
                        "title_en",
                        None,
                    ),
                    sort_order,
                ),
            )

        return chapter_ids

    # ==================================================
    # Sections
    # ==================================================

    @staticmethod
    def _save_sections(
        *,
        cur,
        document: Document,
        document_id: str,
        chapter_ids: set[str],
    ) -> set[str]:

        section_ids: set[str] = set()

        for fallback_order, section in enumerate(
            document.sections,
            start=1,
        ):
            section_id = str(
                section.id
            ).strip()

            if not section_id:
                continue

            if section_id in section_ids:
                continue

            chapter_id = getattr(
                section,
                "chapter_id",
                None,
            )

            if not chapter_id:
                chapter_id = section_id.split(
                    ".",
                    maxsplit=1,
                )[0]

            chapter_id = str(
                chapter_id
            ).strip()

            # 防止孤立 Section 写入数据库
            if chapter_id not in chapter_ids:
                continue

            parent_section_id = getattr(
                section,
                "parent_section_id",
                None,
            )

            if parent_section_id:
                parent_section_id = str(
                    parent_section_id
                ).strip()

            sort_order = getattr(
                section,
                "sort_order",
                None,
            )

            if sort_order is None:
                sort_order = fallback_order

            cur.execute(
                """
                INSERT INTO sections
                (
                    document_id,
                    chapter_id,
                    section_id,
                    parent_section_id,
                    title_jp,
                    title_en,
                    level,
                    sort_order
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                ON CONFLICT
                (
                    document_id,
                    section_id
                )
                DO UPDATE SET
                    chapter_id = EXCLUDED.chapter_id,
                    parent_section_id =
                        EXCLUDED.parent_section_id,
                    title_jp = EXCLUDED.title_jp,
                    title_en = EXCLUDED.title_en,
                    level = EXCLUDED.level,
                    sort_order = EXCLUDED.sort_order
                """,
                (
                    document_id,
                    chapter_id,
                    section_id,
                    parent_section_id,
                    getattr(
                        section,
                        "title_jp",
                        None,
                    ),
                    getattr(
                        section,
                        "title_en",
                        None,
                    ),
                    getattr(
                        section,
                        "level",
                        2,
                    ),
                    sort_order,
                ),
            )

            section_ids.add(
                section_id
            )

        return section_ids

    # ==================================================
    # Contents
    # ==================================================

    @staticmethod
    def _replace_contents(
        *,
        cur,
        document: Document,
        document_id: str,
        chapter_ids: set[str],
        section_ids: set[str],
    ) -> None:
        """
        同一文档重新导入时，删除旧 Chunk 并写入最新 Chunk。

        Chunk 内容发生变化后，原 Embedding 已失效，
        因此重新写入并设为 PENDING。
        """

        cur.execute(
            """
            DELETE FROM contents
            WHERE document_id = %s
            """,
            (
                document_id,
            ),
        )

        used_content_keys: set[
            tuple[str, int]
        ] = set()

        section_chunk_counters: dict[
            str,
            int
        ] = {}

        for content in document.contents:
            text = str(
                getattr(
                    content,
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not text:
                continue

            chapter_id = getattr(
                content,
                "chapter_id",
                None,
            )

            if chapter_id:
                chapter_id = str(
                    chapter_id
                ).strip()

            raw_section_id = getattr(
                content,
                "section_id",
                None,
            )

            if raw_section_id:
                section_id = str(
                    raw_section_id
                ).strip()

                # 引用了不存在的 Section 时，不入库
                if section_id not in section_ids:
                    continue

            elif (
                chapter_id
                and chapter_id in chapter_ids
            ):
                # Chapter 标题下直接存在正文
                section_id = (
                    f"{chapter_id}.ROOT"
                )

            else:
                # 防止 None.ROOT
                continue

            chunk_index = getattr(
                content,
                "chunk_index",
                None,
            )

            if chunk_index is None:
                chunk_index = (
                    section_chunk_counters.get(
                        section_id,
                        0,
                    )
                )

            chunk_index = int(
                chunk_index
            )

            key = (
                section_id,
                chunk_index,
            )

            # 避免违反：
            # UNIQUE(document_id, section_id, chunk_index)
            if key in used_content_keys:
                chunk_index = (
                    section_chunk_counters.get(
                        section_id,
                        0,
                    )
                )

                while (
                    section_id,
                    chunk_index,
                ) in used_content_keys:
                    chunk_index += 1

                key = (
                    section_id,
                    chunk_index,
                )

            used_content_keys.add(
                key
            )

            section_chunk_counters[
                section_id
            ] = chunk_index + 1

            page_number = getattr(
                content,
                "page_number",
                None,
            )

            token_count = getattr(
                content,
                "token_count",
                0,
            )

            if token_count is None:
                token_count = 0

            cur.execute(
                """
                INSERT INTO contents
                (
                    document_id,
                    section_id,
                    content,
                    page_number,
                    chunk_index,
                    token_count,
                    embedding_status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    document_id,
                    section_id,
                    text,
                    page_number,
                    chunk_index,
                    int(token_count),
                    "PENDING",
                ),
            )

    # ==================================================
    # Stale Data Cleanup
    # ==================================================

    @staticmethod
    def _delete_stale_sections(
        *,
        cur,
        document_id: str,
        section_ids: set[str],
    ) -> None:

        if not section_ids:
            cur.execute(
                """
                DELETE FROM sections
                WHERE document_id = %s
                """,
                (
                    document_id,
                ),
            )
            return

        cur.execute(
            """
            DELETE FROM sections
            WHERE document_id = %s
              AND NOT (
                  section_id = ANY(%s)
              )
            """,
            (
                document_id,
                list(section_ids),
            ),
        )

    @staticmethod
    def _delete_stale_chapters(
        *,
        cur,
        document_id: str,
        chapter_ids: set[str],
    ) -> None:

        if not chapter_ids:
            cur.execute(
                """
                DELETE FROM chapters
                WHERE document_id = %s
                """,
                (
                    document_id,
                ),
            )
            return

        cur.execute(
            """
            DELETE FROM chapters
            WHERE document_id = %s
              AND NOT (
                  chapter_id = ANY(%s)
              )
            """,
            (
                document_id,
                list(chapter_ids),
            ),
        )

    # ==================================================
    # Helpers
    # ==================================================

    @staticmethod
    def _resolve_document_id(
        document: Document,
    ) -> str:

        metadata_document_id = (
            document.metadata.get(
                "document_id"
            )
            if document.metadata
            else None
        )

        document_id = (
            metadata_document_id
            or document.file_name
        )

        document_id = str(
            document_id
        ).strip()

        if not document_id:
            raise ValueError(
                "document_id cannot be empty."
            )

        return document_id

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
                "PostgresStorage expects an "
                "app.model.document.Document instance."
            )

        if not document.file_name.strip():
            raise ValueError(
                "Document file_name cannot be empty."
            )

        if not document.file_type.strip():
            raise ValueError(
                "Document file_type cannot be empty."
            )