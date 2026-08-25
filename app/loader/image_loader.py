from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from app.loader.base_loader import BaseLoader
from app.model.block import BlockType, DocumentBlock
from app.model.document import Document
from app.model.page import Page


class ImageLoaderError(RuntimeError):
    """PNG / JPG / JPEG OCR loading error."""


class ImageLoader(BaseLoader):
    """
    Standalone image OCR loader.

    OCR engine:
        RapidOCR + ONNX Runtime

    Supported:
        .png
        .jpg
        .jpeg

    The RapidOCR dependency is imported lazily so PDF/DOCX/PPTX/XLSX/TXT
    processing is unaffected when OCR is not used.
    """

    SUPPORTED_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
    }

    def __init__(
        self,
        *,
        minimum_score: float = 0.50,
    ) -> None:

        if not (
            0.0
            <= minimum_score
            <= 1.0
        ):
            raise ValueError(
                "minimum_score must be between 0 and 1."
            )

        self.minimum_score = float(
            minimum_score
        )

        self._engine = None

    def load(
        self,
        file_path: str | Path,
    ) -> Document:

        path = self._validate_input_path(
            file_path
        )

        try:
            width, height, mode = (
                self._read_image_metadata(
                    path
                )
            )

            engine = (
                self._get_ocr_engine()
            )

            result = engine(
                str(
                    path
                )
            )

            texts = list(
                getattr(
                    result,
                    "txts",
                    ()
                )
                or ()
            )

            scores = list(
                getattr(
                    result,
                    "scores",
                    ()
                )
                or ()
            )

            boxes = getattr(
                result,
                "boxes",
                None,
            )

            box_list: list[
                Any
            ] = []

            if boxes is not None:

                try:
                    box_list = (
                        boxes.tolist()
                    )

                except AttributeError:
                    box_list = list(
                        boxes
                    )

            records: list[
                dict[str, Any]
            ] = []

            for index, raw_text in enumerate(
                texts
            ):

                text = str(
                    raw_text
                    or ""
                ).strip()

                if not text:
                    continue

                score = (
                    float(
                        scores[
                            index
                        ]
                    )
                    if index
                    < len(scores)
                    else 1.0
                )

                if (
                    score
                    < self.minimum_score
                ):
                    continue

                box = (
                    box_list[
                        index
                    ]
                    if index
                    < len(
                        box_list
                    )
                    else None
                )

                top, left = (
                    self._box_sort_position(
                        box
                    )
                )

                records.append(
                    {
                        "source_index": index,
                        "text": text,
                        "score": score,
                        "box": box,
                        "top": top,
                        "left": left,
                    }
                )

            records.sort(
                key=lambda item: (
                    item["top"],
                    item["left"],
                    item["source_index"],
                )
            )

            if not records:
                raise ImageLoaderError(
                    "OCR did not detect readable text "
                    f"with minimum score "
                    f"{self.minimum_score:.2f}."
                )

            blocks: list[
                DocumentBlock
            ] = []

            for order, record in enumerate(
                records
            ):

                blocks.append(
                    DocumentBlock(
                        id=(
                            f"image-ocr-line-"
                            f"{order:08d}"
                        ),
                        block_type=(
                            BlockType.PARAGRAPH
                        ),
                        text=record[
                            "text"
                        ],
                        order=order,
                        page_number=1,
                        source="image_ocr",
                        metadata={
                            "ocr_engine": (
                                "RapidOCR"
                            ),
                            "ocr_score": (
                                record[
                                    "score"
                                ]
                            ),
                            "ocr_box": (
                                record[
                                    "box"
                                ]
                            ),
                            "ocr_source_index": (
                                record[
                                    "source_index"
                                ]
                            ),
                        },
                    )
                )

            page_text = "\n".join(
                block.text
                for block in blocks
            ).strip()

            file_type = (
                path.suffix.lower()
                .lstrip(".")
            )

            return Document(
                file_name=path.name,
                file_type=file_type,
                pages=[
                    Page(
                        page_number=1,
                        text=page_text,
                    )
                ],
                blocks=blocks,
                chapters=[],
                sections=[],
                contents=[],
                metadata={
                    "source_format": (
                        file_type
                    ),
                    "loader": "ImageLoader",
                    "loader_status": "SUCCESS",
                    "ocr_engine": "RapidOCR",
                    "ocr_minimum_score": (
                        self.minimum_score
                    ),
                    "ocr_line_count": len(
                        blocks
                    ),
                    "character_count": len(
                        page_text
                    ),
                    "image_width": width,
                    "image_height": height,
                    "image_mode": mode,
                    "image_size_bytes": (
                        path.stat().st_size
                    ),
                    "ocr_elapse_seconds": (
                        float(
                            getattr(
                                result,
                                "elapse",
                                0.0,
                            )
                            or 0.0
                        )
                    ),
                },
            )

        except ImageLoaderError:
            raise

        except Exception as exc:
            raise ImageLoaderError(
                f"Failed to OCR image "
                f"'{path.name}': {exc}"
            ) from exc

    def _get_ocr_engine(
        self,
    ):

        if self._engine is not None:
            return self._engine

        try:
            from rapidocr import RapidOCR

        except ImportError as exc:
            raise ImageLoaderError(
                "Image OCR dependency is not installed. "
                "Install it with: "
                "python -m pip install rapidocr==3.9.2 onnxruntime"
            ) from exc

        try:
            self._engine = RapidOCR()

        except Exception as exc:
            raise ImageLoaderError(
                "RapidOCR initialization failed: "
                f"{exc}"
            ) from exc

        return self._engine

    @staticmethod
    def _read_image_metadata(
        path: Path,
    ) -> tuple[
        int,
        int,
        str,
    ]:

        try:
            with Image.open(
                path
            ) as image:

                width = int(
                    image.width
                )

                height = int(
                    image.height
                )

                mode = str(
                    image.mode
                )

        except Exception as exc:
            raise ImageLoaderError(
                f"Invalid or unreadable image: "
                f"{exc}"
            ) from exc

        return (
            width,
            height,
            mode,
        )

    @staticmethod
    def _box_sort_position(
        box: Any,
    ) -> tuple[
        float,
        float,
    ]:

        if not box:
            return (
                float("inf"),
                float("inf"),
            )

        try:
            points = [
                (
                    float(
                        point[0]
                    ),
                    float(
                        point[1]
                    ),
                )
                for point in box
                if (
                    point is not None
                    and len(
                        point
                    )
                    >= 2
                )
            ]

        except Exception:
            return (
                float("inf"),
                float("inf"),
            )

        if not points:
            return (
                float("inf"),
                float("inf"),
            )

        left = min(
            point[0]
            for point in points
        )

        top = min(
            point[1]
            for point in points
        )

        return (
            top,
            left,
        )

    @classmethod
    def _validate_input_path(
        cls,
        file_path: str | Path,
    ) -> Path:

        path = Path(
            file_path
        ).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"Image file not found: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Input path is not a file: {path}"
            )

        if (
            path.suffix.lower()
            not in cls.SUPPORTED_EXTENSIONS
        ):
            raise ValueError(
                "ImageLoader only accepts "
                ".png/.jpg/.jpeg files. "
                f"Received: "
                f"{path.suffix or '<no extension>'}"
            )

        return path
