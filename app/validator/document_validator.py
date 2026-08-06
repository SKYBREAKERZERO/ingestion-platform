class DocumentValidator:


    def validate(
        self,
        document
    ):

        warnings = []

        errors = []


        # =========================
        # Chapter ID检查
        # =========================

        chapter_ids = set()


        for chapter in document.chapters:


            if chapter.id in chapter_ids:

                warnings.append(
                    f"Duplicate chapter detected: {chapter.id}"
                )


            chapter_ids.add(
                chapter.id
            )



        # =========================
        # Section ID检查
        # =========================

        section_ids = set()


        for section in document.sections:


            if section.id in section_ids:

                warnings.append(
                    f"Duplicate section detected: {section.id}"
                )


            section_ids.add(
                section.id
            )



        # =========================
        # 空Section检查
        # =========================

        content_section_ids = set()


        for content in document.contents:


            if content.section_id:

                content_section_ids.add(
                    content.section_id
                )



        for section in document.sections:


            if section.id not in content_section_ids:


                warnings.append(

                    f"Empty section: {section.id}"

                )



        return {


            "valid":
                len(errors) == 0,


            "errors":
                errors,


            "warnings":
                warnings

        }