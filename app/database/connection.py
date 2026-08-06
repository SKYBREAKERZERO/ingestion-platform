import psycopg



class DatabaseConnection:


    def __init__(

        self,

        host="localhost",

        port=5432,

        database="rag",

        user="postgres",

        password="12345"

    ):

        self.config = {

            "host": host,

            "port": port,

            "dbname": database,

            "user": user,

            "password": password

        }



    def connect(self):

        return psycopg.connect(

            **self.config

        )