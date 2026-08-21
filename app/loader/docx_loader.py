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
from app.model.block import (
    BlockType,
    DocumentBlock,
)
from app.model.document import Document
from app.model.page import Page


class DOCXLoaderError(RuntimeError):
    """
    DOCX 文件加载异常。
    """


class DOCXLoader(BaseLoader):
    """
    DOCX 原始内容加载器。

    负责：
        - 按 Word 原始顺序读取段落和表格
        - 保留标题样式和标题层级
        - 保留表格 Cell 列位置
        - 保留重复 Cell
        - 输出统一 Document.pages
        - 输出结构化 Document.blocks
        - 保存基础元数据

    不负责：
        - Chapter / Section 建模
        - Paragraph 内容过滤
        - Table 内容过滤
        - 标题合并
        - Chunk
        - Token 统计
        - JSON / PostgreSQL 保存

    设计原则：
        Loader 负责尽量无损地读取原始结构。

        是否删除：
            - 空 Cell
            - 重复 Cell
            - 空段落
            - 噪声

        应交给后续 Filter 决定。

        Loader 不应提前做不可恢复的数据删除。
    """

    # ==================================================
    # Heading Style
    # ==================================================

    _HEADING_STYLE_PATTERN = re.compile(
        r"^(?:heading|見出し|标题|標題)\s*([1-9]\d*)$",
        re.IGNORECASE,
    )

    # ==================================================
    # Public API
    # ==================================================

    def load(
        self,
        file_path: str,
    ) -> Document:
        """
        加载 DOCX 文件。

        Args:
            file_path:
                DOCX 文件路径。

        Returns:
            原始结构化 Document。
        """

        path = self._validate_path(
            file_path
        )

        try:

            word_document = WordDocument(
                str(path)
            )

            return self._build_document(
                path=path,
                word_document=word_document,
            )

        except DOCXLoaderError:
            raise

        except Exception as exc:

            raise DOCXLoaderError(
                "Failed to load DOCX file "
                f"'{path.name}': {exc}"
            ) from exc

    # ==================================================
    # Build Document
    # ==================================================

    def _build_document(
        self,
        *,
        path: Path,
        word_document: WordDocumentType,
    ) -> Document:

        blocks: list[
            DocumentBlock
        ] = []

        plain_text_lines: list[
            str
        ] = []

        paragraph_count = 0
        heading_count = 0
        list_count = 0

        table_count = 0
        table_row_count = 0

        empty_table_cell_count = 0
        table_cell_count = 0

        order = 0

        # ==============================================
        # Original Word Order
        # ==============================================

        for raw_block in self._iter_blocks(
            word_document
        ):

            # ==========================================
            # Paragraph
            # ==========================================

            if isinstance(
                raw_block,
                Paragraph,
            ):

                text = self._normalize_text(
                    raw_block.text
                )

                # 当前 Loader 不建立空 Paragraph Block。
                #
                # 空段落通常只承担 Word 排版作用，
                # 对后续 RAG 没有检索价值。
                if not text:
                    continue

                style_name = (
                    self._get_style_name(
                        raw_block
                    )
                )

                heading_level = (
                    self._get_heading_level(
                        style_name
                    )
                )

                # ======================================
                # Block Type
                # ======================================

                if heading_level is not None:

                    block_type = (
                        BlockType.HEADING
                    )

                    heading_count += 1

                elif self._is_list_paragraph(
                    raw_block
                ):

                    block_type = (
                        BlockType.LIST
                    )

                    list_count += 1

                else:

                    block_type = (
                        BlockType.PARAGRAPH
                    )

                # ======================================
                # Block
                # ======================================

                block = DocumentBlock(
                    block_type=block_type,
                    text=text,
                    level=heading_level,
                    style_name=style_name,
                    order=order,
                    source="docx",
                    metadata={
                        "source": "paragraph",
                    },
                )

                blocks.append(
                    block
                )

                plain_text_lines.append(
                    text
                )

                paragraph_count += 1
                order += 1

                continue

            # ==========================================
            # Table
            # ==========================================

            if isinstance(
                raw_block,
                Table,
            ):

                current_table_index = (
                    table_count
                )

                table_count += 1

                for (
                    row_index,
                    row,
                ) in enumerate(
                    raw_block.rows
                ):

                    # ==================================
                    # Extract Cells
                    # ==================================
                    #
                    # 注意：
                    #
                    # 不删除空 Cell。
                    # 不删除重复 Cell。
                    #
                    # Loader 必须保留原始列位置。

                    values = (
                        self._extract_row_values(
                            row.cells
                        )
                    )

                    table_cell_count += len(
                        values
                    )

                    empty_table_cell_count += sum(
                        1
                        for value
                        in values
                        if not value
                    )

                    # ==================================
                    # Completely Empty Row
                    # ==================================
                    #
                    # 空行没有建立 Block 的必要。
                    #
                    # 但只要存在任意 Cell 内容，
                    # 就必须完整保留所有 Cell 位置。

                    if not any(
                        values
                    ):
                        continue

                    # ==================================
                    # Display Text
                    # ==================================

                    row_text = (
                        self._build_row_text(
                            values
                        )
                    )

                    # ==================================
                    # Block
                    # ==================================

                    block = DocumentBlock(
                        block_type=BlockType.TABLE,
                        text=row_text,
                        order=order,
                        table_index=(
                            current_table_index
                        ),
                        row_index=row_index,
                        cells=values,
                        source="docx",
                        metadata={
                            "source": "table",
                            "table_index": (
                                current_table_index
                            ),
                            "row_index": (
                                row_index
                            ),
                            "column_count": (
                                len(values)
                            ),
                            "non_empty_cell_count": (
                                sum(
                                    1
                                    for value
                                    in values
                                    if value
                                )
                            ),
                        },
                    )

                    blocks.append(
                        block
                    )

                    plain_text_lines.append(
                        row_text
                    )

                    table_row_count += 1
                    order += 1

        # ==============================================
        # Logical Page
        # ==============================================
        #
        # DOCX 当前统一采用一个逻辑 Page。
        #
        # 后续：
        #
        #   ParagraphFilter
        #   TableFilter
        #   HeadingMerger
        #
        # 修改 blocks 后会重新同步 pages[0]。

        content = "\n".join(
            plain_text_lines
        ).strip()

        # ==============================================
        # Metadata
        # ==============================================

        metadata = {
            "source_format": "docx",

            "loader": (
                "DOCXLoader"
            ),

            "loader_status": (
                "SUCCESS"
            ),

            "paragraph_count": (
                paragraph_count
            ),

            "heading_count": (
                heading_count
            ),

            "list_count": (
                list_count
            ),

            "table_count": (
                table_count
            ),

            "table_row_count": (
                table_row_count
            ),

            "table_cell_count": (
                table_cell_count
            ),

            "empty_table_cell_count": (
                empty_table_cell_count
            ),

            "block_count": (
                len(blocks)
            ),

            "character_count": (
                len(content)
            ),
        }

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

    # ==================================================
    # Path Validation
    # ==================================================

    @staticmethod
    def _validate_path(
        file_path: str,
    ) -> Path:

        if not file_path:

            raise ValueError(
                "file_path cannot be empty."
            )

        path = Path(
            file_path
        ).expanduser()

        if not path.exists():

            raise FileNotFoundError(
                f"DOCX file not found: {path}"
            )

        if not path.is_file():

            raise IsADirectoryError(
                "Input path is not a file: "
                f"{path}"
            )

        # Word 打开的临时文件。
        if path.name.startswith(
            "~$"
        ):

            raise ValueError(
                "Temporary Word file "
                "is not supported: "
                f"{path.name}"
            )

        if (
            path.suffix.lower()
            != ".docx"
        ):

            raise ValueError(
                "DOCXLoader only accepts "
                ".docx files. "
                f"Received: "
                f"{path.suffix or '<no extension>'}"
            )

        return path

    # ==================================================
    # Normalize Text
    # ==================================================

    @staticmethod
    def _normalize_text(
        text: str | None,
    ) -> str:
        """
        Loader 级别的轻量文本标准化。

        这里只处理明显的空白差异。

        更全面的 Unicode 清洗由：
            UnicodeNormalizer

        负责。
        """

        if text is None:
            return ""

        normalized = str(
            text
        )

        normalized = (
            normalized.replace(
                "\u3000",
                " ",
            )
        )

        normalized = (
            normalized.replace(
                "\xa0",
                " ",
            )
        )

        normalized = (
            normalized.replace(
                "\r\n",
                "\n",
            )
        )

        normalized = (
            normalized.replace(
                "\r",
                "\n",
            )
        )

        # ==============================================
        # Preserve Meaningful Multiline Content
        # ==============================================
        #
        # Word Cell 内可能包含多个 Paragraph：
        #
        #   AAA
        #   BBB
        #
        # 统一成：
        #
        #   AAA / BBB
        #
        # 避免直接压缩成 "AAA BBB"，
        # 保留一定的内部结构信息。

        lines = [
            " ".join(
                line.split()
            )
            for line
            in normalized.splitlines()
            if line.strip()
        ]

        return " / ".join(
            lines
        ).strip()

    # ==================================================
    # Style Name
    # ==================================================

    @staticmethod
    def _get_style_name(
        paragraph: Paragraph,
    ) -> str | None:

        style = (
            paragraph.style
        )

        if style is None:
            return None

        name = getattr(
            style,
            "name",
            None,
        )

        if not name:
            return None

        normalized = str(
            name
        ).strip()

        return (
            normalized
            or None
        )

    # ==================================================
    # Heading Level
    # ==================================================

    @classmethod
    def _get_heading_level(
        cls,
        style_name: str | None,
    ) -> int | None:

        if not style_name:
            return None

        normalized = (
            cls._normalize_text(
                style_name
            )
        )

        match = (
            cls._HEADING_STYLE_PATTERN.fullmatch(
                normalized
            )
        )

        if match is None:
            return None

        return int(
            match.group(1)
        )

    # ==================================================
    # List Detection
    # ==================================================

    @staticmethod
    def _is_list_paragraph(
        paragraph: Paragraph,
    ) -> bool:
        """
        判断 Paragraph 是否包含 Word 编号或项目符号属性。
        """

        properties = (
            paragraph._p.pPr
        )

        if properties is None:
            return False

        return (
            properties.numPr
            is not None
        )

    # ==================================================
    # Extract Table Row
    # ==================================================

    @classmethod
    def _extract_row_values(
        cls,
        cells,
    ) -> list[str]:
        """
        提取一行所有 Cell。

        重要：
            保留空 Cell。
            保留相同文本 Cell。

        Example:

            Word:
                A |   | C

            Result:
                ["A", "", "C"]

        Example:

            Word:
                ON | ON | OFF

            Result:
                ["ON", "ON", "OFF"]

        Loader 不进行 Cell 去重。
        """

        values: list[
            str
        ] = []

        for cell in cells:

            value = (
                cls._normalize_text(
                    cell.text
                )
            )

            values.append(
                value
            )

        return values

    # ==================================================
    # Build Row Text
    # ==================================================

    @staticmethod
    def _build_row_text(
        values: list[str],
    ) -> str:
        """
        构建用于 Page / Block 的逻辑表格文本。

        Cell 数组本身仍保留完整列结构。

        Example:

            ["A", "", "C"]

        Text:

            A |  | C
        """

        return " | ".join(
            values
        ).strip()

    # ==================================================
    # Iterate Word Blocks
    # ==================================================

    @staticmethod
    def _iter_blocks(
        document: WordDocumentType,
    ) -> Iterator[
        Paragraph | Table
    ]:
        """
        按 document.xml 中原始顺序遍历：

            Paragraph
            Table

        从而避免：

            document.paragraphs
            document.tables

        分开读取后破坏原始顺序。
        """

        parent_element = (
            document.element.body
        )

        for child in (
            parent_element.iterchildren()
        ):

            if isinstance(
                child,
                CT_P,
            ):

                yield Paragraph(
                    child,
                    document,
                )

            elif isinstance(
                child,
                CT_Tbl,
            ):

                yield Table(
                    child,
                    document,
                )