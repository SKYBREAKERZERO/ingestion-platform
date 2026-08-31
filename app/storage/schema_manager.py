from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

import psycopg
from psycopg import sql


RAG_SCHEMA_VERSION = 3
RAG_SCHEMA_NAME = "rag-schema-v3"


class SchemaManagerError(RuntimeError):
    """PostgreSQL RAG schema initialization / verification error."""


@dataclass(frozen=True, slots=True)
class SchemaReport:
    ready: bool
    version: int | None
    required_tables: tuple[str, ...]
    available_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    required_views: tuple[str, ...]
    available_views: tuple[str, ...]
    missing_views: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    created_objects: tuple[str, ...] = ()
    equivalent_indexes_reused: tuple[str, ...] = ()
    duplicate_index_groups: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def status_text(self) -> str:
        if self.ready:
            base = (
                f"RAG Schema v{self.version or RAG_SCHEMA_VERSION} ready | "
                f"Tables {len(self.available_tables)}/{len(self.required_tables)} | "
                f"Views {len(self.available_views)}/{len(self.required_views)}"
            )
            if self.duplicate_index_groups:
                base += (
                    f"\nLegacy duplicate index groups: "
                    f"{len(self.duplicate_index_groups)} (left untouched)"
                )
            return base

        parts = ["RAG schema is not ready"]
        if self.missing_tables:
            parts.append("Missing tables: " + ", ".join(self.missing_tables))
        if self.missing_views:
            parts.append("Missing views: " + ", ".join(self.missing_views))
        if self.missing_columns:
            for table_name, columns in self.missing_columns.items():
                parts.append(
                    f"{table_name} missing columns: " + ", ".join(columns)
                )
        return "\n".join(parts)


class SchemaManager:
    """
    Non-destructive PostgreSQL schema manager for the ingestion/RAG platform.

    Responsibilities:
        - create fresh RAG tables
        - upgrade existing ingestion tables by adding missing columns
        - create only useful RAG/worker indexes
        - avoid creating an index when an equivalent B-Tree already exists
        - create the rag_chunks read view
        - record schema version
        - audit duplicate legacy indexes without automatically dropping them

    This manager never executes DROP TABLE, TRUNCATE or DELETE against business
    data. Legacy duplicate indexes are reported but not automatically removed.
    """

    REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
        "documents": {
            "id",
            "document_id",
            "file_name",
            "file_type",
            "title",
            "module",
            "metadata",
            "created_at",
            "updated_at",
        },
        "chapters": {
            "id",
            "document_id",
            "chapter_id",
            "title_jp",
            "title_en",
            "sort_order",
            "metadata",
            "created_at",
            "updated_at",
        },
        "sections": {
            "id",
            "document_id",
            "chapter_id",
            "section_id",
            "parent_section_id",
            "title_jp",
            "title_en",
            "level",
            "sort_order",
            "page_number",
            "metadata",
            "created_at",
            "updated_at",
        },
        "contents": {
            "id",
            "document_id",
            "chapter_id",
            "section_id",
            "content",
            "page_number",
            "chunk_index",
            "token_count",
            "sort_order",
            "metadata",
            "content_hash",
            "embedding_status",
            "embedding_started_at",
            "embedded_at",
            "embedding_model",
            "embedding_version",
            "embedded_content_hash",
            "embedding_error",
            "embedding_retry_count",
            "created_at",
            "updated_at",
        },
        "embeddings": {
            "id",
            "content_id",
            "model_name",
            "model_version",
            "vector_dimension",
            "qdrant_collection",
            "qdrant_point_id",
            "content_hash",
            "created_at",
            "updated_at",
        },
        "vector_delete_queue": {
            "id",
            "content_id",
            "document_id",
            "reason",
            "queued_at",
            "processed_at",
            "last_error",
        },
        "schema_version": {
            "component",
            "version",
            "name",
            "applied_at",
        },
    }

    REQUIRED_VIEWS = ("rag_chunks",)

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        connect_timeout: int = 10,
        database_connection: Any | None = None,
    ) -> None:
        self.database_connection = database_connection
        self.host = str(host or "").strip()
        self.port = int(port or 5432)
        self.database = str(database or "").strip()
        self.user = str(user or "").strip()
        self.password = password
        self.connect_timeout = int(connect_timeout)

        if self.database_connection is None:
            missing = [
                name
                for name, value in (
                    ("host", self.host),
                    ("database", self.database),
                    ("user", self.user),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Missing PostgreSQL connection settings: "
                    + ", ".join(missing)
                )
            if self.connect_timeout <= 0:
                raise ValueError("connect_timeout must be greater than 0.")

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.database_connection is not None:
            with self.database_connection.connect() as connection:
                yield connection
            return

        with psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=self.connect_timeout,
            application_name="document-ingestion-schema-manager",
        ) as connection:
            yield connection

    def ensure_schema(self) -> SchemaReport:
        created: list[str] = []
        reused: list[str] = []
        warnings: list[str] = []

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    self._create_base_tables(cursor, created)
                    self._upgrade_columns(cursor, created)
                    self._backfill_compatibility_columns(cursor)
                    self._backfill_content_chapter(cursor)
                    self._ensure_constraints_and_indexes(
                        cursor,
                        created=created,
                        reused=reused,
                        warnings=warnings,
                    )
                    self._create_rag_view(cursor, created)
                    self._record_schema_version(cursor)
                connection.commit()
        except Exception as exc:
            raise SchemaManagerError(
                f"Failed to initialize / upgrade RAG schema: {exc}"
            ) from exc

        report = self.inspect_schema()
        return SchemaReport(
            ready=report.ready,
            version=report.version,
            required_tables=report.required_tables,
            available_tables=report.available_tables,
            missing_tables=report.missing_tables,
            required_views=report.required_views,
            available_views=report.available_views,
            missing_views=report.missing_views,
            missing_columns=report.missing_columns,
            created_objects=tuple(created),
            equivalent_indexes_reused=tuple(reused),
            duplicate_index_groups=report.duplicate_index_groups,
            warnings=tuple(warnings) + report.warnings,
        )

    def inspect_schema(self) -> SchemaReport:
        required_tables = tuple(self.REQUIRED_TABLE_COLUMNS)

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_type = 'BASE TABLE'
                        """
                    )
                    table_names = {row[0] for row in cursor.fetchall()}

                    cursor.execute(
                        """
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = ANY(%s)
                        """,
                        (list(required_tables),),
                    )
                    columns: dict[str, set[str]] = {
                        table: set() for table in required_tables
                    }
                    for table_name, column_name in cursor.fetchall():
                        if table_name in columns:
                            columns[table_name].add(column_name)

                    cursor.execute(
                        """
                        SELECT table_name
                        FROM information_schema.views
                        WHERE table_schema = 'public'
                        """
                    )
                    view_names = {row[0] for row in cursor.fetchall()}

                    version = self._read_schema_version(cursor)
                    duplicate_groups = self._find_duplicate_index_groups(cursor)
        except Exception as exc:
            raise SchemaManagerError(
                f"Failed to inspect RAG schema: {exc}"
            ) from exc

        missing_tables = tuple(
            table for table in required_tables if table not in table_names
        )
        available_tables = tuple(
            table for table in required_tables if table in table_names
        )
        missing_views = tuple(
            view for view in self.REQUIRED_VIEWS if view not in view_names
        )
        available_views = tuple(
            view for view in self.REQUIRED_VIEWS if view in view_names
        )

        missing_columns: dict[str, tuple[str, ...]] = {}
        for table, expected in self.REQUIRED_TABLE_COLUMNS.items():
            if table not in table_names:
                continue
            missing = tuple(sorted(expected - columns.get(table, set())))
            if missing:
                missing_columns[table] = missing

        ready = (
            not missing_tables
            and not missing_views
            and not missing_columns
            and version == RAG_SCHEMA_VERSION
        )

        return SchemaReport(
            ready=ready,
            version=version,
            required_tables=required_tables,
            available_tables=available_tables,
            missing_tables=missing_tables,
            required_views=self.REQUIRED_VIEWS,
            available_views=available_views,
            missing_views=missing_views,
            missing_columns=missing_columns,
            duplicate_index_groups=tuple(duplicate_groups),
        )

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------

    def _create_base_tables(self, cursor: Any, created: list[str]) -> None:
        statements: Sequence[tuple[str, str]] = (
            (
                "schema_version",
                """
                CREATE TABLE IF NOT EXISTS public.schema_version (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
            ),
            (
                "documents",
                """
                CREATE TABLE IF NOT EXISTS public.documents (
                    id BIGSERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    title TEXT,
                    module TEXT,
                    document_type TEXT,
                    version TEXT,
                    company TEXT,
                    category TEXT,
                    source_file TEXT,
                    language JSONB,
                    source_hash TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_documents_document_id UNIQUE (document_id)
                )
                """,
            ),
            (
                "chapters",
                """
                CREATE TABLE IF NOT EXISTS public.chapters (
                    id BIGSERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chapter_id TEXT NOT NULL,
                    title_jp TEXT,
                    title_en TEXT,
                    sort_order INTEGER,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_chapters_document_chapter
                        UNIQUE (document_id, chapter_id),
                    CONSTRAINT fk_chapters_document
                        FOREIGN KEY (document_id)
                        REFERENCES public.documents(document_id)
                        ON DELETE CASCADE
                )
                """,
            ),
            (
                "sections",
                """
                CREATE TABLE IF NOT EXISTS public.sections (
                    id BIGSERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chapter_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    parent_section_id TEXT,
                    title_jp TEXT,
                    title_en TEXT,
                    level INTEGER NOT NULL DEFAULT 2,
                    sort_order INTEGER,
                    page_number INTEGER,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_sections_document_section
                        UNIQUE (document_id, section_id),
                    CONSTRAINT fk_sections_document
                        FOREIGN KEY (document_id)
                        REFERENCES public.documents(document_id)
                        ON DELETE CASCADE
                )
                """,
            ),
            (
                "contents",
                """
                CREATE TABLE IF NOT EXISTS public.contents (
                    id BIGSERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chapter_id TEXT,
                    section_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    page_number INTEGER,
                    chunk_index INTEGER NOT NULL DEFAULT 0,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    content_hash TEXT,
                    embedding_status TEXT NOT NULL DEFAULT 'PENDING',
                    embedding_started_at TIMESTAMPTZ,
                    embedded_at TIMESTAMPTZ,
                    embedding_model TEXT,
                    embedding_version TEXT,
                    embedded_content_hash TEXT,
                    embedding_error TEXT,
                    embedding_retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_contents_document_section_chunk
                        UNIQUE (document_id, section_id, chunk_index),
                    CONSTRAINT fk_contents_document
                        FOREIGN KEY (document_id)
                        REFERENCES public.documents(document_id)
                        ON DELETE CASCADE
                )
                """,
            ),
            (
                "embeddings",
                """
                CREATE TABLE IF NOT EXISTS public.embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    content_id BIGINT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL DEFAULT 'dense-v1',
                    vector_dimension INTEGER NOT NULL DEFAULT 1024,
                    qdrant_collection TEXT NOT NULL DEFAULT 'document_chunks',
                    qdrant_point_id TEXT NOT NULL,
                    content_hash TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_embeddings_content_model_version
                        UNIQUE (content_id, model_name, model_version),
                    CONSTRAINT fk_embeddings_content
                        FOREIGN KEY (content_id)
                        REFERENCES public.contents(id)
                        ON DELETE CASCADE
                )
                """,
            ),
            (
                "vector_delete_queue",
                """
                CREATE TABLE IF NOT EXISTS public.vector_delete_queue (
                    id BIGSERIAL PRIMARY KEY,
                    content_id BIGINT NOT NULL,
                    document_id TEXT,
                    reason TEXT NOT NULL DEFAULT 'STALE_CONTENT',
                    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    processed_at TIMESTAMPTZ,
                    last_error TEXT,
                    CONSTRAINT uq_vector_delete_queue_content UNIQUE (content_id)
                )
                """,
            ),
        )

        for name, statement in statements:
            existed = self._relation_exists(cursor, name, kinds=("r", "p"))
            cursor.execute(statement)
            if not existed:
                created.append(f"table:{name}")

    def _upgrade_columns(self, cursor: Any, created: list[str]) -> None:
        upgrades: dict[str, Sequence[tuple[str, str]]] = {
            "documents": (
                ("file_name", "TEXT"),
                ("file_type", "TEXT"),
                ("title", "TEXT"),
                ("module", "TEXT"),
                ("document_type", "TEXT"),
                ("version", "TEXT"),
                ("company", "TEXT"),
                ("category", "TEXT"),
                ("source_file", "TEXT"),
                ("language", "JSONB"),
                ("source_hash", "TEXT"),
                ("metadata", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
                ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ),
            "chapters": (
                ("metadata", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
                ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ),
            "sections": (
                ("parent_section_id", "TEXT"),
                ("page_number", "INTEGER"),
                ("metadata", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
                ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ),
            "contents": (
                ("chapter_id", "TEXT"),
                ("sort_order", "INTEGER"),
                ("metadata", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
                ("content_hash", "TEXT"),
                ("embedding_status", "TEXT NOT NULL DEFAULT 'PENDING'"),
                ("embedding_started_at", "TIMESTAMPTZ"),
                ("embedded_at", "TIMESTAMPTZ"),
                ("embedding_model", "TEXT"),
                ("embedding_version", "TEXT"),
                ("embedded_content_hash", "TEXT"),
                ("embedding_error", "TEXT"),
                ("embedding_retry_count", "INTEGER NOT NULL DEFAULT 0"),
                ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ),
            "embeddings": (
                ("content_id", "BIGINT"),
                ("model_name", "TEXT"),
                ("model_version", "TEXT NOT NULL DEFAULT 'dense-v1'"),
                ("vector_dimension", "INTEGER NOT NULL DEFAULT 1024"),
                ("qdrant_collection", "TEXT NOT NULL DEFAULT 'document_chunks'"),
                ("qdrant_point_id", "TEXT"),
                ("content_hash", "TEXT"),
                ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ),
        }

        for table_name, definitions in upgrades.items():
            if not self._relation_exists(cursor, table_name, kinds=("r", "p")):
                continue
            existing = self._table_columns(cursor, table_name)
            for column_name, definition in definitions:
                if column_name in existing:
                    continue
                cursor.execute(
                    sql.SQL("ALTER TABLE public.{} ADD COLUMN {} {}").format(
                        sql.Identifier(table_name),
                        sql.Identifier(column_name),
                        sql.SQL(definition),
                    )
                )
                created.append(f"column:{table_name}.{column_name}")
                existing.add(column_name)

    @staticmethod
    def _backfill_compatibility_columns(cursor: Any) -> None:
        cursor.execute(
            """
            UPDATE public.documents
            SET file_name = COALESCE(NULLIF(file_name, ''), title, document_id),
                file_type = COALESCE(NULLIF(file_type, ''), module, document_type, 'unknown')
            WHERE file_name IS NULL
               OR file_name = ''
               OR file_type IS NULL
               OR file_type = ''
            """
        )

    @staticmethod
    def _backfill_content_chapter(cursor: Any) -> None:
        cursor.execute(
            """
            UPDATE public.contents c
            SET chapter_id = s.chapter_id
            FROM public.sections s
            WHERE c.chapter_id IS NULL
              AND s.document_id = c.document_id
              AND s.section_id = c.section_id
            """
        )

    def _ensure_constraints_and_indexes(
        self,
        cursor: Any,
        *,
        created: list[str],
        reused: list[str],
        warnings: list[str],
    ) -> None:
        desired = (
            ("uq_documents_document_id", "documents", ("document_id",), True),
            (
                "uq_chapters_document_chapter",
                "chapters",
                ("document_id", "chapter_id"),
                True,
            ),
            (
                "uq_sections_document_section",
                "sections",
                ("document_id", "section_id"),
                True,
            ),
            (
                "uq_contents_document_section_chunk",
                "contents",
                ("document_id", "section_id", "chunk_index"),
                True,
            ),
            (
                "idx_sections_document_chapter",
                "sections",
                ("document_id", "chapter_id"),
                False,
            ),
            (
                "idx_sections_parent",
                "sections",
                ("document_id", "parent_section_id"),
                False,
            ),
            (
                "idx_contents_document_order",
                "contents",
                ("document_id", "id"),
                False,
            ),
            (
                "idx_contents_embedding_queue",
                "contents",
                ("embedding_status", "id"),
                False,
            ),
            (
                "idx_contents_embedding_stale",
                "contents",
                ("embedding_status", "embedding_started_at"),
                False,
            ),
            (
                "uq_embeddings_content_model_version",
                "embeddings",
                ("content_id", "model_name", "model_version"),
                True,
            ),
            (
                "idx_embeddings_content",
                "embeddings",
                ("content_id",),
                False,
            ),
            (
                "uq_vector_delete_queue_content",
                "vector_delete_queue",
                ("content_id",),
                True,
            ),
            (
                "idx_vector_delete_queue_pending",
                "vector_delete_queue",
                ("processed_at", "id"),
                False,
            ),
        )

        for name, table, columns, unique in desired:
            if not self._all_columns_exist(cursor, table, columns):
                warnings.append(
                    f"Skipped index {name}: missing columns on {table}."
                )
                continue
            equivalent = self._find_equivalent_index(
                cursor,
                table_name=table,
                columns=columns,
                unique=unique,
            )
            if equivalent:
                reused.append(f"{name} -> {equivalent}")
                continue

            unique_sql = sql.SQL("UNIQUE ") if unique else sql.SQL("")
            cursor.execute(
                sql.SQL("CREATE {}INDEX {} ON public.{} USING btree ({})").format(
                    unique_sql,
                    sql.Identifier(name),
                    sql.Identifier(table),
                    sql.SQL(", ").join(sql.Identifier(col) for col in columns),
                )
            )
            created.append(f"index:{name}")

    @staticmethod
    def _create_rag_view(cursor: Any, created: list[str]) -> None:
        existed = False
        cursor.execute("SELECT to_regclass('public.rag_chunks')")
        existed = cursor.fetchone()[0] is not None

        cursor.execute(
            """
            CREATE OR REPLACE VIEW public.rag_chunks AS
            SELECT
                c.id AS content_id,
                c.document_id,
                COALESCE(NULLIF(d.file_name, ''), d.title, d.document_id) AS file_name,
                COALESCE(NULLIF(d.file_type, ''), d.module, d.document_type) AS file_type,
                COALESCE(c.chapter_id, s.chapter_id) AS chapter_id,
                ch.title_jp AS chapter_title_jp,
                ch.title_en AS chapter_title_en,
                COALESCE(NULLIF(ch.title_jp, ''), ch.title_en) AS chapter_title,
                c.section_id,
                s.parent_section_id,
                s.title_jp AS section_title_jp,
                s.title_en AS section_title_en,
                COALESCE(NULLIF(s.title_jp, ''), s.title_en) AS section_title,
                s.level AS section_level,
                c.page_number,
                c.chunk_index,
                c.sort_order,
                c.token_count,
                c.content,
                c.content_hash,
                c.embedding_status,
                c.embedding_started_at,
                c.embedded_at,
                c.embedding_model,
                c.embedding_version,
                c.embedded_content_hash,
                c.embedding_retry_count,
                c.embedding_error,
                c.created_at,
                c.updated_at
            FROM public.contents c
            LEFT JOIN public.documents d
              ON d.document_id = c.document_id
            LEFT JOIN public.sections s
              ON s.document_id = c.document_id
             AND s.section_id = c.section_id
            LEFT JOIN public.chapters ch
              ON ch.document_id = c.document_id
             AND ch.chapter_id = COALESCE(c.chapter_id, s.chapter_id)
            """
        )
        if not existed:
            created.append("view:rag_chunks")

    @staticmethod
    def _record_schema_version(cursor: Any) -> None:
        cursor.execute(
            """
            INSERT INTO public.schema_version(component, version, name, applied_at)
            VALUES ('document_ingestion_rag', %s, %s, NOW())
            ON CONFLICT (component)
            DO UPDATE SET
                version = EXCLUDED.version,
                name = EXCLUDED.name,
                applied_at = EXCLUDED.applied_at
            """,
            (RAG_SCHEMA_VERSION, RAG_SCHEMA_NAME),
        )

    @staticmethod
    def _read_schema_version(cursor: Any) -> int | None:
        if not SchemaManager._relation_exists(
            cursor, "schema_version", kinds=("r", "p")
        ):
            return None
        cursor.execute(
            """
            SELECT version
            FROM public.schema_version
            WHERE component = 'document_ingestion_rag'
            """
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None

    # ------------------------------------------------------------------
    # Catalog helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relation_exists(cursor: Any, name: str, kinds: tuple[str, ...]) -> bool:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = %s
                  AND c.relkind = ANY(%s)
            )
            """,
            (name, list(kinds)),
        )
        return bool(cursor.fetchone()[0])

    @staticmethod
    def _table_columns(cursor: Any, table_name: str) -> set[str]:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            """,
            (table_name,),
        )
        return {row[0] for row in cursor.fetchall()}

    @classmethod
    def _all_columns_exist(
        cls,
        cursor: Any,
        table_name: str,
        columns: Sequence[str],
    ) -> bool:
        actual = cls._table_columns(cursor, table_name)
        return all(column in actual for column in columns)

    @staticmethod
    def _find_equivalent_index(
        cursor: Any,
        *,
        table_name: str,
        columns: Sequence[str],
        unique: bool,
    ) -> str | None:
        cursor.execute(
            """
            SELECT
                idx.relname AS index_name,
                i.indisunique,
                array_agg(att.attname ORDER BY keys.ordinality) AS columns
            FROM pg_index i
            JOIN pg_class tbl ON tbl.oid = i.indrelid
            JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
            JOIN pg_class idx ON idx.oid = i.indexrelid
            JOIN pg_am am ON am.oid = idx.relam
            JOIN LATERAL unnest(i.indkey)
                WITH ORDINALITY AS keys(attnum, ordinality) ON TRUE
            JOIN pg_attribute att
              ON att.attrelid = tbl.oid
             AND att.attnum = keys.attnum
            WHERE ns.nspname = 'public'
              AND tbl.relname = %s
              AND am.amname = 'btree'
              AND i.indpred IS NULL
              AND i.indexprs IS NULL
            GROUP BY idx.relname, i.indisunique
            """,
            (table_name,),
        )
        wanted = tuple(columns)
        for index_name, is_unique, index_columns in cursor.fetchall():
            if bool(is_unique) != bool(unique):
                continue
            if tuple(index_columns or ()) == wanted:
                return str(index_name)
        return None

    @staticmethod
    def _find_duplicate_index_groups(cursor: Any) -> list[str]:
        cursor.execute(
            """
            SELECT
                tbl.relname AS table_name,
                idx.relname AS index_name,
                i.indisunique,
                i.indisprimary,
                array_agg(att.attname ORDER BY keys.ordinality) AS columns
            FROM pg_index i
            JOIN pg_class tbl ON tbl.oid = i.indrelid
            JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
            JOIN pg_class idx ON idx.oid = i.indexrelid
            JOIN pg_am am ON am.oid = idx.relam
            JOIN LATERAL unnest(i.indkey)
                WITH ORDINALITY AS keys(attnum, ordinality) ON TRUE
            JOIN pg_attribute att
              ON att.attrelid = tbl.oid
             AND att.attnum = keys.attnum
            WHERE ns.nspname = 'public'
              AND am.amname = 'btree'
              AND i.indpred IS NULL
              AND i.indexprs IS NULL
              AND tbl.relname IN (
                    'documents', 'chapters', 'sections', 'contents',
                    'embeddings', 'vector_delete_queue'
              )
            GROUP BY tbl.relname, idx.relname, i.indisunique, i.indisprimary
            ORDER BY tbl.relname, idx.relname
            """
        )

        groups: dict[tuple[str, bool, tuple[str, ...]], list[str]] = {}
        for table, index_name, is_unique, _is_primary, columns in cursor.fetchall():
            key = (str(table), bool(is_unique), tuple(columns or ()))
            groups.setdefault(key, []).append(str(index_name))

        result: list[str] = []
        for (table, is_unique, columns), names in groups.items():
            if len(names) <= 1:
                continue
            result.append(
                f"{table} ({'UNIQUE ' if is_unique else ''}"
                f"{', '.join(columns)}): {', '.join(names)}"
            )
        return result
