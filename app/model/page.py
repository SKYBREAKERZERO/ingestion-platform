from pydantic import BaseModel

class Page(BaseModel):

    page_number: int

    text: str
