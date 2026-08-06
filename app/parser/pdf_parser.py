from __future__ import annotations

from app.analyzer.structure_analyzer import StructureAnalyzer
from app.model.document import Document


class PDFParser:
    """
    PDF 文档结构解析器。

    责任：
        1. 接收 PDFLoader 生成的 Document。
        2. 调用 StructureAnalyzer 解析章节、节和正文。
        3. 写入解析器相关 metadata。
        4. 返回统一 Document 模型。

    不负责：
        - 读取 PDF 文件
        - 删除目录页
        - 删除页眉页脚
        - 内容分块
        - token 统计
        - JSON 或数据库保存
    """

    def __init__(
        self,
        structure_analyzer: StructureAnalyzer | None = None,
    ) -> None:

        self.structure_analyzer = (
            structure_analyzer
            or StructureAnalyzer()
        )

    def parse(
        self,
        document: Document,
    ) -> Document:

        self._validate_document(
            document
        )

        # 防止同一个 Document 实例被重复解析时累积旧结果。
        document.chapters.clear()
        document.sections.clear()
        document.contents.clear()

        parsed_document = (
            self.structure_analyzer.analyze(
                document
            )
        )

        parsed_document.metadata.update(
            {
                "parser": "PDFParser",
                "parser_status": "SUCCESS",
                "parsed_page_count": len(
                    parsed_document.pages
                ),
                "chapter_count": len(
                    parsed_document.chapters
                ),
                "section_count": len(
                    parsed_document.sections
                ),
                "content_count": len(
                    parsed_document.contents
                ),
            }
        )

        return parsed_document

    @staticmethod
    def _validate_document(
        document: Document,
    ) -> None:

        if document is None:

            raise ValueError(
                "Document cannot be None."
            )

        if not isinstance(
            document,
            Document,
        ):

            raise TypeError(
                "PDFParser expects an "
                "app.model.document.Document instance."
            )

        if document.file_type.lower() != "pdf":

            raise ValueError(
                "PDFParser only accepts PDF documents. "
                f"Received file_type: {document.file_type}"
            )

        if not document.pages:

            raise ValueError(
                "PDF document contains no pages."
            )

        if not any(
            page.text.strip()
            for page in document.pages
        ):

            raise ValueError(
                "PDF document contains no extractable text. "
                "The file may be scanned and require OCR."
            )