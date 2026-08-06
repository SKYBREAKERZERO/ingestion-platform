class Chunker:


    def __init__(
        self,
        max_length=1000
    ):

        self.max_length = max_length



    def process(
        self,
        document
    ):


        new_contents=[]


        for content in document.contents:


            text = content.text.strip()


            if len(text) <= self.max_length:

                new_contents.append(
                    content
                )

                continue



            chunks = [

                text[i:i+self.max_length]

                for i in range(
                    0,
                    len(text),
                    self.max_length
                )

            ]


            for index,chunk in enumerate(chunks):


                new_content = content.model_copy()


                new_content.text = chunk

                new_content.chunk_index = index


                new_contents.append(
                    new_content
                )



        document.contents = new_contents


        return document