from pydantic import BaseModel


class Model(BaseModel):
    """
    Shared base for all Patcher Pydantic models.

    Subclasses inherit Pydantic 2's default validation and serialization
    behavior. This wrapper exists so the project has a single import-point
    for the project-wide model base, making future config (e.g. shared
    ``model_config`` settings, computed-field policy) easier to apply in
    one place.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
