from pathlib import Path
import openpyxl
from app.loader.base_loader import BaseLoader
from app.model.document import (
    Document,
    Page
)

class ExcelLoader(BaseLoader):

    def load(
        self,
        file_path:str
    )->Document:

        workbook = openpyxl.load_workbook(
            file_path
        )

        texts=[]

        for sheet in workbook:

            texts.append(
                f"Sheet:{sheet.title}"
            )

            for row in sheet.iter_rows(
                values_only=True
            ):

                line=" ".join(
                    [
                        str(x)
                        for x in row
                        if x
                    ]
                )

                if line:
                    texts.append(line)

        return Document(

            file_name=
                Path(file_path).name,

            file_type="xlsx",

            pages=[
                Page(
                    page_number=1,
                    text="\n".join(texts)
                )
            ]

        )