class Deduplicator:



    def process(

        self,

        document

    ):


        self.merge_chapters(

            document

        )


        self.merge_sections(

            document

        )


        return document



    def merge_chapters(

        self,

        document

    ):


        unique = {}

        result = []



        for chapter in document.chapters:


            if chapter.id not in unique:


                unique[chapter.id] = chapter

                result.append(

                    chapter

                )


        document.chapters = result



    def merge_sections(

        self,

        document

    ):


        unique = {}

        result = []



        for section in document.sections:


            key = section.id



            if key not in unique:


                unique[key] = section

                result.append(

                    section

                )


        document.sections = result