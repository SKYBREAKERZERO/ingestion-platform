from __future__ import annotations

from app.model.document import Document
from app.parser.structured_text_parser import StructuredTextParser


class ImageParser:
    """OCR text -> Chapter / Section / Content."""

    SUPPORTED_FILE_TYPES = {
        "png",
        "jpg",
        "jpeg",
    }

    def __init__(
        self,
    ) -> None:

        self._parser = (
            StructuredTextParser(
                parser_name="ImageParser"
            )
        )

    def parse(
        self,
        document: Document,
    ) -> Document:

        if (
            document.file_type.lower()
            not in self.SUPPORTED_FILE_TYPES
        ):
            raise ValueError(
                "ImageParser only accepts "
                "PNG/JPG/JPEG documents. "
                f"Received: {document.file_type}"
            )

        return self._parser.parse(
            document
        )
