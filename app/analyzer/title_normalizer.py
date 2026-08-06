class TitleNormalizer:


    def normalize(self, text):


        lines = [

            x.strip()

            for x in text.splitlines()

            if x.strip()

        ]


        result=[]


        i=0



        while i < len(lines):


            current = lines[i]



            # 日文字符断行

            if i + 1 < len(lines):


                nxt = lines[i+1]



                if self.should_merge(

                    current,

                    nxt

                ):


                    current += nxt

                    i += 1



            result.append(current)


            i += 1



        return "\n".join(result)



    def should_merge(

        self,

        current,

        next_line

    ):


        # 当前行太长不处理

        if len(current) > 25:

            return False



        # 下一行太长不处理

        if len(next_line) > 25:

            return False



        # 当前没有结束符

        if current.endswith(

            ("。","．",".","！","？")

        ):

            return False



        # 下一行不是章节

        import re


        if re.match(

            r"^[0-9０-９]+[\.．]",

            next_line

        ):

            return False



        # 日文断词

        if (

            current[-1:].isascii()

            == False

        ):


            return True



        return False