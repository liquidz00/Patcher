"""
Pydantic schema for the Installomator label-generation endpoint.

Labels are uniquely an Installomator artifact — there's no "format" variant
to choose here. If we ever emit a different patch-management format (Jamf
Title Editor JSON, AutoPkg recipe, etc.), it goes behind a dedicated endpoint
with its own response shape, not as a format toggle here.
"""

from pydantic import BaseModel, ConfigDict


class GenerateLabelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_name: str
    content: str
    sources_used: list[str]
    warnings: list[str]
