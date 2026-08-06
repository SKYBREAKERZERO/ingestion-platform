class SectionHierarchyBuilder:


    def process(
        self,
        document
    ):


        # =====================
        # 建立section索引
        # =====================

        section_map = {

            section.id: section

            for section in document.sections

        }



        # =====================
        # 设置父节点
        # =====================

        for section in document.sections:


            parent_id = self.find_parent(

                section.id

            )


            if parent_id in section_map:


                section.parent_section_id = parent_id


            else:


                section.parent_section_id = None



        return document




    def find_parent(
        self,
        section_id
    ):


        parts = section_id.split(".")



        # chapter级别

        if len(parts) <= 1:

            return None



        # 删除最后一级

        return ".".join(

            parts[:-1]

        )