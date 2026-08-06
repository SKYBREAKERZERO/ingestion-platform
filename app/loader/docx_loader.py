from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from docx import Document as WordDocument
from docx.document import Document as WordDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.loader.base_loader import BaseLoader
from app.model.block import BlockType, DocumentBlock
from app.model.document import Document
from app.model.page import Page


class DOCXLoader(BaseLoader):
    """
    DOCX 原始内容加载器。

    负责：
        - 按 Word 原始顺序读取段落和表格
        - 保留标题样式和标题层级
        - 输出统一 Document.pages
        - 输出结构化 Document.blocks
        - 保存基础元数据

    不负责：
        - Chapter / Section 建模
        - 内容过滤
        - Chunk
        - Token 统计
        - JSON / PostgreSQL 保存
    """

    _HEADING_STYLE_PATTERN = re.compile(
        r"^(?:heading|見出し|标题|標題)\s*([1-9]\d*)$",
        re.IGNORECASE,
    )

    def load(
        self,
        file_path: str,
    ) -> Document:

        path = self._validate_path(
            file_path
        )

        word_document = WordDocument(
            str(path)
        )

        blocks: list[DocumentBlock] = []
        plain_text_lines: list[str] = []

        paragraph_count = 0
        heading_count = 0
        table_count = 0
        table_row_count = 0

        order = 0

        for raw_block in self._iter_blocks(
            word_document
        ):
            if isinstance(raw_block, Paragraph):
                text = self._normalize_text(
                    raw_block.text
                )

                if not text:
                    continue

                style_name = self._get_style_name(
                    raw_block
                )

                heading_level = self._get_heading_level(
                    style_name
                )

                if heading_level is not None:
                    block_type = BlockType.HEADING
                    heading_count += 1
                elif self._is_list_paragraph(raw_block):
                    block_type = BlockType.LIST
                else:
                    block_type = BlockType.PARAGRAPH

                blocks.append(
                    DocumentBlock(
                        block_type=block_type,
                        text=text,
                        level=heading_level,
                        style_name=style_name,
                        order=order,
                        metadata={
                            "source": "paragraph",
                        },
                    )
                )

                plain_text_lines.append(text)

                paragraph_count += 1
                order += 1
                continue

            if isinstance(raw_block, Table):
                current_table_index = table_count
                table_count += 1

                for row_index, row in enumerate(
                    raw_block.rows
                ):
                    values = self._extract_row_values(
                        row.cells
                    )

                    if not values:
                        continue

                    row_text = " | ".join(values)

                    blocks.append(
                        DocumentBlock(
                            block_type=BlockType.TABLE,
                            text=row_text,
                            order=order,
                            table_index=current_table_index,
                            row_index=row_index,
                            cells=values,
                            metadata={
                                "source": "table",
                            },
                        )
                    )

                    plain_text_lines.append(row_text)

                    table_row_count += 1
                    order += 1

        content = "\n".join(
            plain_text_lines
        ).strip()

        metadata = {
            "source_format": "docx",
            "paragraph_count": paragraph_count,
            "heading_count": heading_count,
            "table_count": table_count,
            "table_row_count": table_row_count,
            "block_count": len(blocks),
            "character_count": len(content),
            "loader": "DOCXLoader",
            "loader_status": "SUCCESS",
        }

        print()
        print("===== DOCX Loader =====")
        print(f"File       : {path.name}")
        print(f"Paragraphs : {paragraph_count}")
        print(f"Headings   : {heading_count}")
        print(f"Tables     : {table_count}")
        print(f"Table rows : {table_row_count}")
        print(f"Blocks     : {len(blocks)}")
        print(f"Characters : {len(content)}")
        print("=======================")
        print()

        return Document(
            file_name=path.name,
            file_type="docx",
            pages=[
                Page(
                    page_number=1,
                    text=content,
                )
            ],
            blocks=blocks,
            metadata=metadata,
        )

    @staticmethod
    def _validate_path(
        file_path: str,
    ) -> Path:

        path = Path(file_path).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"DOCX file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        if path.suffix.lower() != ".docx":
            raise ValueError(
                "DOCXLoader only accepts .docx files. "
                f"Received: {path.suffix or '<no extension>'}"
            )

        return path

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:

        if not text:
            return ""

        normalized = text.replace(
            "\u3000",
            " ",
        )

        normalized = normalized.replace(
            "\xa0",
            " ",
        )

        return " ".join(
            normalized.split()
        )

    @staticmethod
    def _get_style_name(
        paragraph: Paragraph,
    ) -> str | None:

        style = paragraph.style

        if style is None:
            return None

        name = getattr(
            style,
            "name",
            None,
        )

        if not name:
            return None

        return str(name).strip() or None

    @classmethod
    def _get_heading_level(
        cls,
        style_name: str | None,
    ) -> int | None:

        if not style_name:
            return None

        normalized = cls._normalize_text(
            style_name
        )

        match = cls._HEADING_STYLE_PATTERN.match(
            normalized
        )

        if match is None:
            return None

        return int(
            match.group(1)
        )

    @staticmethod
    def _is_list_paragraph(
        paragraph: Paragraph,
    ) -> bool:
        """
        判断段落是否包含 Word 编号或项目符号属性。
        """

        properties = paragraph._p.pPr

        if properties is None:
            return False

        return properties.numPr is not None

    @classmethod
    def _extract_row_values(
        cls,
        cells,
    ) -> list[str]:

        values: list[str] = []
        previous_value: str | None = None

        for cell in cells:
            value = cls._normalize_text(
                cell.text
            )

            if not value:
                continue

            # 合并单元格可能导致 python-docx 重复返回相同文本。
            if value == previous_value:
                continue

            values.append(value)
            previous_value = value

        return values

    @staticmethod
    def _iter_blocks(
        document: WordDocumentType,
    ) -> Iterator[Paragraph | Table]:
        """
        按 document.xml 中的原始顺序遍历段落和表格。
        """

        parent_element = document.element.body

        for child in parent_element.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(
                    child,
                    document,
                )

            elif isinstance(child, CT_Tbl):
                yield Table(
                    child,
                    document,
                )