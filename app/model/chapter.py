from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Chapter(BaseModel):
    """
    文档 Chapter。

    示例：
        1  Introduction
        2  System Overview
        8  Performance
    """

    # =====================
    # Identity
    # =====================

    id: str

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