from pydantic import BaseModel


class Model(BaseModel):
    def __init__(self, **kwargs):
        """"""
        super().__init__(**kwargs)
