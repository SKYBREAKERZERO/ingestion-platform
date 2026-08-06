import re


class TokenCounter:


    def __init__(self):

        pass



    def process(
        self,
        document
    ):


        for content in document.contents:


            content.token_count = self.count(

                content.text

            )


        return document




    def count(
        self,
        text
    ):


        if not text:

            return 0



        # =====================
        # 简易token估算
        # =====================
        #
        # 日文/中文:
        # 一个字符≈一个token
        #
        # 英文:
        # 一个单词≈1~2 token
        #
        # 企业RAG初期足够
        # =====================


        japanese_chars = len(

            re.findall(

                r'[\u3040-\u30ff\u3400-\u9fff]',

                text

            )

        )


        english_words = len(

            re.findall(

                r'[a-zA-Z]+',

                text

            )

        )


        numbers = len(

            re.findall(

                r'\d+',

                text

            )

        )



        return (

            japanese_chars

            +

            english_words

            +

            numbers

        )