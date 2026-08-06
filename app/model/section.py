from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Section(BaseModel):
    """
    文档 Section。

    示例：

        4.1
        4.1.2
        4.1.2.1
    """

    # =====================
    # Identity
    # =====================

    id: str

    chapter_id: str | None = None

    parent_section_id: str | None = None

    # =====================
    # Titles
    # =====================

    title_jp: str | None = None

    title_en: str | None = None

    # =====================
    # Structure
    # =====================

    level: int = 1

    sort_order: int = 0

    # =====================
    # Location
    # =====================

    page_number: int | None = None

    # =====================
    # Metadata
    # =====================

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )