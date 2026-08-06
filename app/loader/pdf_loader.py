from pathlib import Path

import fitz

from app.loader.base_loader import BaseLoader

from app.model.document import (
    Document,
    Page
)

from app.utils.exceptions import (
    FileReadException
)


class PDFLoader(BaseLoader):


    def load(
        self,
        file_path: str
    ) -> Document:


        try:

            pages = []


            with fitz.open(
                file_path
            ) as pdf:


                for index, page in enumerate(
                    pdf,
                    start=1
                ):

                    text = (
                        page
                        .get_text()
                        .strip()
                    )


                    pages.append(

                        Page(

                            page_number=index,

                            text=text

                        )

                    )


                metadata = {

                    "page_count":
                        len(pdf),

                    "pdf_metadata":
                        pdf.metadata

                }

            return Document(

                file_name=
                    Path(file_path).name,

                file_type="pdf",

                pages=pages,

                metadata=metadata

            )

        except Exception as e:

            raise FileReadException(

                f"Failed to read PDF: {file_path}. "
                f"Reason: {str(e)}"

            )