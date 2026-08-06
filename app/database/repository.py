from app.database.connection import DatabaseConnection



class PostgresStorage:


    def __init__(self):

        self.db = DatabaseConnection()



    def save_document(

        self,

        document

    ):


        with self.db.connect() as conn:


            with conn.cursor() as cur:


                cur.execute(

                    """
                    INSERT INTO documents
                    (
                        file_name,
                        file_type
                    )
                    VALUES
                    (
                        %s,
                        %s
                    )
                    RETURNING id
                    """,

                    (

                        document.file_name,

                        document.file_type

                    )

                )


                document_id = cur.fetchone()[0]


        return document_id