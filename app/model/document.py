from typing import Optional

from pydantic import BaseModel, Field

from app.model.page import Page
from app.model.block import DocumentBlock
from app.model.chapter import Chapter
from app.model.section import Section
from app.model.content import Content


class Document(BaseModel):

    # =====================
    # Basic Information
    # =====================

    file_name: str

    file_type: str

    # =====================
    # Raw Pages (PDF)
    # =====================

    pages: list[Page] = Field(
        default_factory=list
    )

    # =====================
    # Raw Blocks (DOCX / PPTX / XLSX ...)
    # =====================

    blocks: list[DocumentBlock] = Field(
        default_factory=list
    )

    # =====================
    # Structure
    # =====================

    chapters: list[Chapter] = Field(
        default_factory=list
    )

    sections: list[Section] = Field(
        default_factory=list
    )

    # =====================
    # Processed Contents
    # =====================

    contents: list[Content] = Field(
        default_factory=list
    )

    # =====================
    # Metadata
    # =====================

    metadata: dict = Field(
        default_factory=dict
    )