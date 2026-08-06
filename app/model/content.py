from pydantic import BaseModel
from typing import Optional


class Content(BaseModel):

    chapter_id: Optional[str] = None

    section_id: Optional[str] = None

    text: str

    page_number: Optional[int] = None

    chunk_index: int = 0

    token_count: int = 0