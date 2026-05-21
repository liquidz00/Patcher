from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    """
    Shared base for all Patcher Pydantic models.

    Subclasses inherit Pydantic 2's default validation and serialization
    behavior. This wrapper exists so the project has a single import-point
    for the project-wide model base, making future config (e.g. shared
    ``model_config`` settings, computed-field policy) easier to apply in
    one place.
    """


class UpstreamModel(Model):
    """
    Base for models that mirror an external camelCase schema.

    Use this when the field names are dictated by an upstream source
    (Jamf API responses, Installomator label scripts, etc.) but Python
    callers should still use snake_case attribute access.

    Configures the model so that:

    - **Field names are snake_case** (Pythonic attribute access).
    - **Aliases are auto-generated as camelCase** via Pydantic's
      :func:`pydantic.alias_generators.to_camel`, so constructing from
      an upstream dict (``MyModel(**raw_dict)`` or
      ``MyModel.model_validate(raw_dict)``) Just Works.
    - **``populate_by_name=True``** lets callers pass either the
      snake_case field name *or* the camelCase alias on construction,
      whichever is more convenient.

    ``to_camel`` follows standard camelCase rules (``expected_team_id`` →
    ``expectedTeamId``). For fields whose upstream name has an all-caps
    acronym (e.g. Installomator's ``expectedTeamID`` or ``downloadURL``),
    override the alias explicitly with ``Field(..., alias="expectedTeamID")``
    on that field. Explicit ``Field(alias=...)`` takes precedence over the
    generator.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
