import re


class PageFilter:

    def filter(
        self,
        document
    ):

        # =====================
        # Only PDF needs page filtering
        # =====================

        if document.file_type.lower() != "pdf":

            return document

        pages = []

        for page in document.pages:

            text = page.text.strip()

            if not text:
                continue

            lines = [

                line.strip()

                for line in text.splitlines()

                if line.strip()

            ]

            title_count = sum(

                1

                for line in lines

                if self.is_title(line)

            )

            # =====================
            # TOC Page
            # =====================

            if title_count >= 10:

                continue

            pages.append(page)

        document.pages = pages

        return document

    def is_title(
        self,
        line
    ):

        pattern = (

            r"^[0-9０-９]+"

            r"(?:[\.．][0-9０-９]+){0,3}"

            r"\s+"

        )

        return bool(

            re.match(

                pattern,

                line

            )

        )