from pathlib import Path


from app.loader.pdf_loader import PDFLoader

from app.loader.docx_loader import DOCXLoader

from app.loader.excel_loader import ExcelLoader



class LoaderFactory:



    @staticmethod
    def get_loader(file_path):


        ext = Path(file_path).suffix.lower()



        if ext == ".pdf":

            return PDFLoader()



        if ext == ".docx":

            return DOCXLoader()



        if ext in [".xlsx",".xls"]:

            return ExcelLoader()



        raise Exception(

            f"Unsupported file:{ext}"

        )