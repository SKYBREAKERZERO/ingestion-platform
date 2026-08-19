from __future__ import annotations

import logging
from typing import Sequence

from qdrant_client import (
    QdrantClient,
)

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.vector.base import (
    VectorRecord,
    VectorSearchResult,
    VectorStore,
    VectorStoreError,
    VectorStoreValidationError,
)


LOGGER = logging.getLogger(
    "document_ingestion.vector.qdrant"
)


class QdrantVectorStoreError(
    VectorStoreError
):
    """
    Qdrant Vector Store 异常。
    """


class QdrantVectorStore(
    VectorStore
):
    """
    Qdrant Vector Store 实现。

    当前设计：

        PostgreSQL
            =
        Source of Truth

        Qdrant
            =
        Vector Search Index

    Qdrant Payload 保存：

        content_id
        document_id
        section_id
        page_number
        chunk_index
        token_count
        model_name

    完整正文仍然以 PostgreSQL contents 为准。
    """

    def __init__(
        self,
        *,
        url: str = "http://127.0.0.1:6333",
        collection_name: str = "document_chunks",
        dimension: int = 1024,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:

        self.url = self._normalize_required_string(
            url,
            field_name="url",
        )

        self.collection_name = (
            self._normalize_required_string(
                collection_name,
                field_name="collection_name",
            )
        )

        if dimension <= 0:
            raise VectorStoreValidationError(
                "dimension must be greater than 0."
            )

        if timeout <= 0:
            raise VectorStoreValidationError(
                "timeout must be greater than 0."
            )

        self.dimension = int(
            dimension
        )

        self.timeout = int(
            timeout
        )

        try:
            self.client = (
                QdrantClient(
                    url=self.url,
                    api_key=api_key,
                    timeout=self.timeout,
                )
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to initialize "
                f"Qdrant client: {exc}"
            ) from exc

    # ==================================================
    # Collection
    # ==================================================

    def ensure_collection(
        self,
    ) -> None:
        """
        Collection 不存在时创建。

        当前使用：
            COSINE

        BGE-M3 Dense Embedding：
            1024 dimensions
        """

        try:
            exists = (
                self.client
                .collection_exists(
                    collection_name=(
                        self.collection_name
                    )
                )
            )

            if exists:
                self._validate_collection()

                return

            self.client.create_collection(
                collection_name=(
                    self.collection_name
                ),
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE,
                ),
            )

            LOGGER.info(
                "Qdrant collection created | "
                "collection=%s | "
                "dimension=%s",
                self.collection_name,
                self.dimension,
            )

        except QdrantVectorStoreError:
            raise

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to ensure Qdrant "
                f"collection "
                f"'{self.collection_name}': "
                f"{exc}"
            ) from exc

    # ==================================================
    # Upsert
    # ==================================================

    def upsert(
        self,
        records: Sequence[
            VectorRecord
        ],
    ) -> int:
        """
        批量 Upsert。

        同一 Point ID：
            Update

        新 Point ID：
            Insert
        """

        normalized_records = (
            self._validate_records(
                records
            )
        )

        if not normalized_records:
            return 0

        points = [
            PointStruct(
                id=record.id,
                vector=record.vector,
                payload=record.payload,
            )
            for record in normalized_records
        ]

        try:
            self.client.upsert(
                collection_name=(
                    self.collection_name
                ),
                points=points,
                wait=True,
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to upsert vectors "
                f"into collection "
                f"'{self.collection_name}': "
                f"{exc}"
            ) from exc

        LOGGER.info(
            "Qdrant vectors upserted | "
            "collection=%s | "
            "count=%s",
            self.collection_name,
            len(points),
        )

        return len(
            points
        )

    # ==================================================
    # Search
    # ==================================================

    def search(
        self,
        query_vector: Sequence[float],
        *,
        limit: int = 10,
        document_id: str | None = None,
    ) -> list[VectorSearchResult]:
        """
        Cosine Similarity Search。

        可选：

            document_id

        用于只在某个文档范围内检索。
        """

        vector = self._validate_vector(
            query_vector
        )

        if limit <= 0:
            raise VectorStoreValidationError(
                "limit must be greater than 0."
            )

        query_filter = None

        if document_id is not None:
            normalized_document_id = (
                self._normalize_required_string(
                    document_id,
                    field_name="document_id",
                )
            )

            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(
                            value=(
                                normalized_document_id
                            )
                        ),
                    )
                ]
            )

        try:
            response = (
                self.client
                .query_points(
                    collection_name=(
                        self.collection_name
                    ),
                    query=vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to search Qdrant "
                f"collection "
                f"'{self.collection_name}': "
                f"{exc}"
            ) from exc

        results: list[
            VectorSearchResult
        ] = []

        for point in response.points:
            results.append(
                VectorSearchResult(
                    id=point.id,
                    score=float(
                        point.score
                    ),
                    payload=dict(
                        point.payload
                        or {}
                    ),
                )
            )

        return results

    # ==================================================
    # Delete
    # ==================================================

    def delete_by_document(
        self,
        document_id: str,
    ) -> None:

        normalized_document_id = (
            self._normalize_required_string(
                document_id,
                field_name="document_id",
            )
        )

        try:
            self.client.delete(
                collection_name=(
                    self.collection_name
                ),
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(
                                value=(
                                    normalized_document_id
                                )
                            ),
                        )
                    ]
                ),
                wait=True,
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to delete vectors "
                f"for document "
                f"'{normalized_document_id}': "
                f"{exc}"
            ) from exc

        LOGGER.info(
            "Qdrant document vectors deleted | "
            "document_id=%s",
            normalized_document_id,
        )

    # ==================================================
    # Count
    # ==================================================

    def count(
        self,
    ) -> int:

        try:
            result = (
                self.client.count(
                    collection_name=(
                        self.collection_name
                    ),
                    exact=True,
                )
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to count Qdrant "
                f"vectors: {exc}"
            ) from exc

        return int(
            result.count
        )

    # ==================================================
    # Collection Validation
    # ==================================================

    def _validate_collection(
        self,
    ) -> None:
        """
        防止 Collection 已存在，
        但 Vector Dimension 与当前模型不一致。

        例如：

            Collection = 768维
            BGE-M3     = 1024维

        此时禁止继续写入。
        """

        try:
            info = (
                self.client
                .get_collection(
                    collection_name=(
                        self.collection_name
                    )
                )
            )

        except Exception as exc:
            raise QdrantVectorStoreError(
                "Failed to inspect Qdrant "
                f"collection: {exc}"
            ) from exc

        vectors_config = (
            info.config
            .params
            .vectors
        )

        actual_dimension = getattr(
            vectors_config,
            "size",
            None,
        )

        if (
            actual_dimension is not None
            and int(
                actual_dimension
            ) != self.dimension
        ):
            raise QdrantVectorStoreError(
                "Qdrant collection vector "
                "dimension mismatch. "
                f"collection="
                f"{self.collection_name}, "
                f"expected={self.dimension}, "
                f"actual={actual_dimension}"
            )

    # ==================================================
    # Validation
    # ==================================================

    def _validate_records(
        self,
        records: Sequence[
            VectorRecord
        ],
    ) -> list[VectorRecord]:

        if records is None:
            raise VectorStoreValidationError(
                "records cannot be None."
            )

        normalized: list[
            VectorRecord
        ] = []

        seen_ids: set[
            int | str
        ] = set()

        for index, record in enumerate(
            records
        ):
            if not isinstance(
                record,
                VectorRecord,
            ):
                raise VectorStoreValidationError(
                    "Invalid VectorRecord "
                    f"at index {index}."
                )

            if record.id in seen_ids:
                continue

            self._validate_vector(
                record.vector
            )

            if not isinstance(
                record.payload,
                dict,
            ):
                raise VectorStoreValidationError(
                    "VectorRecord payload "
                    "must be dict."
                )

            seen_ids.add(
                record.id
            )

            normalized.append(
                record
            )

        return normalized

    def _validate_vector(
        self,
        vector: Sequence[float],
    ) -> list[float]:

        if vector is None:
            raise VectorStoreValidationError(
                "vector cannot be None."
            )

        try:
            normalized = [
                float(value)
                for value in vector
            ]

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreValidationError(
                "vector must contain "
                "numeric values."
            ) from exc

        if (
            len(normalized)
            != self.dimension
        ):
            raise VectorStoreValidationError(
                "Vector dimension mismatch. "
                f"expected={self.dimension}, "
                f"actual={len(normalized)}"
            )

        return normalized

    @staticmethod
    def _normalize_required_string(
        value: str,
        *,
        field_name: str,
    ) -> str:

        normalized = str(
            value
            or ""
        ).strip()

        if not normalized:
            raise VectorStoreValidationError(
                f"{field_name} "
                "cannot be empty."
            )

        return normalized