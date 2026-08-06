from app.loader.loader_factory import LoaderFactory


from app.filter.pdf.page_filter import PageFilter
from app.filter.pdf.header_footer_filter import HeaderFooterFilter
from app.filter.common.content_filter import ContentFilter


from app.analyzer.structure_analyzer import StructureAnalyzer


from app.processor.deduplicator import Deduplicator
from app.processor.section_hierarchy import SectionHierarchyBuilder
from app.processor.chunker import Chunker
from app.processor.token_counter import TokenCounter


from app.builder.json_builder import JsonBuilder


from app.storage.postgres_storage import PostgresStorage





class IngestionPipeline:



    def __init__(self):


        # =====================
        # Filters
        # =====================

        self.page_filter = PageFilter()

        self.header_footer_filter = HeaderFooterFilter()

        self.content_filter = ContentFilter()



        # =====================
        # Analyzer
        # =====================

        self.analyzer = StructureAnalyzer()



        # =====================
        # Processors
        # =====================

        self.deduplicator = Deduplicator()


        self.section_hierarchy = (
            SectionHierarchyBuilder()
        )


        self.chunker = Chunker(

            max_length=1000

        )


        self.token_counter = TokenCounter()



        # =====================
        # Output
        # =====================

        self.builder = JsonBuilder()


        self.storage = PostgresStorage()





    def run(

        self,

        file_path,

        output

    ):



        # =====================
        # 1. Load
        # =====================

        loader = LoaderFactory.get_loader(

            file_path

        )


        document = loader.load(

            file_path

        )



        # =====================
        # 2. Page Filtering
        # =====================

        document = self.page_filter.filter(

            document

        )



        # =====================
        # 3. Header Footer Removal
        # =====================

        document = (
            self.header_footer_filter.filter(
                document
            )
        )



        # =====================
        # 4. Structure Analysis
        # =====================

        document = self.analyzer.analyze(

            document

        )



        # =====================
        # 5. Remove Duplicate
        # =====================

        document = self.deduplicator.process(

            document

        )



        # =====================
        # 6. Build Section Tree
        # =====================

        document = (
            self.section_hierarchy.process(
                document
            )
        )



        # =====================
        # 7. Remove Invalid Content
        # =====================

        document = (
            self.content_filter.filter(
                document
            )
        )



        # =====================
        # 8. Split Chunk
        # =====================

        document = (
            self.chunker.process(
                document
            )
        )



        # =====================
        # 9. Token Count
        # =====================

        document = (
            self.token_counter.process(
                document
            )
        )



        # =====================
        # 10. JSON Export
        # =====================

        json_data = self.builder.build(

            document

        )


        self.builder.save(

            json_data,

            output

        )



        # =====================
        # 11. Database
        # =====================

        self.storage.save(

            document

        )



        return document