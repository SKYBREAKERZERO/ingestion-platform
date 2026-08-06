import re



class TitleJoiner:


    """
    PDF title line joiner.

    Responsibility:
        Fix broken titles caused by PDF extraction.

    Example:

        2 デバイス
        Setting

    ->

        2 デバイス Setting


    Do NOT:

        2 Playback Function
        2.1 Start Method

    merge.

    """



    def join(
        self,
        lines
    ):


        result = []


        index = 0



        while index < len(lines):


            current = lines[index].strip()



            if not current:

                index += 1

                continue



            merged = False



            # =========================
            # Try merge title fragment
            # =========================

            if self.is_possible_title(current):


                if index + 1 < len(lines):


                    next_line = lines[index + 1].strip()



                    if self.should_merge(

                        current,

                        next_line

                    ):


                        current = (

                            current

                            + " "

                            + next_line

                        )


                        index += 1


                        merged = True





            result.append(

                current

            )


            index += 1



        return result






    def is_possible_title(
        self,
        line
    ):


        """
        Check current line starts with title number.

        Examples:

        1 Title
        1.1 Title
        １．１ Title

        """


        pattern = (

            r"^[0-9０-９]+"

            r"([\.．][0-9０-９]+)*"

            r"[\s　]+"

            r".+"

        )


        return bool(

            re.match(

                pattern,

                line

            )

        )








    def should_merge(
        self,
        current,
        next_line
    ):


        """
        Strict merge decision.

        Conservative:
        false > wrong merge.
        """



        if not next_line:


            return False




        # =================================
        # 1. Next line is another heading
        # =================================


        if self.is_heading_line(

            next_line

        ):


            return False





        # =================================
        # 2. Page number
        # =================================


        if re.match(

            r"^\d+/\d+$",

            next_line

        ):


            return False






        # =================================
        # 3. Current title too long
        # =================================


        if len(current) > 40:


            return False





        # =================================
        # 4. Next line too long
        # Usually body text
        # =================================


        if len(next_line) > 25:


            return False





        # =================================
        # 5. Next line ending punctuation
        # Body sentence
        # =================================


        if next_line.endswith(

            (

                "。",

                "．",

                ".",

                "！",

                "？",

                "ます",

                "です"

            )

        ):


            return False






        # =================================
        # 6. Body text keyword detection
        # =================================


        body_keywords = [

            "について",

            "参照",

            "以下",

            "本仕様書",

            "機能",

            "場合",

            "方法",

        ]



        for keyword in body_keywords:


            if keyword in next_line:


                return False





        # =================================
        # 7. Title fragment rules
        # =================================


        if len(next_line) <= 15:


            return True






        # English title continuation

        if re.match(

            r"^[A-Za-z\s\-]+$",

            next_line

        ):


            return True






        return False







    def is_heading_line(
        self,
        line
    ):


        """
        Detect next line is another chapter/section title.
        """


        pattern = (

            r"^[0-9０-９]+"

            r"([\.．][0-9０-９]+)+"

            r"[\s　]+"

            r".+"

        )



        return bool(

            re.match(

                pattern,

                line

            )

        )