from __future__ import annotations

from app.model.document import Document
from app.parser.structured_text_parser import StructuredTextParser


class TXTParser:
    """TXT structure parser."""

    def __init__(
        self,
    ) -> None:

        self._parser = (
            StructuredTextParser(
                parser_name="TXTParser"
            )
        )

    def parse(
        self,
        document: Document,
    ) -> Document:

        if (
            document.file_type.lower()
            != "txt"
        ):
            raise ValueError(
                "TXTParser only accepts TXT documents. "
                f"Received: {document.file_type}"
            )

        return self._parser.parse(
            document
        )
