"""
Pydantic schema for the Installomator label-generation endpoint.

Labels are uniquely an Installomator artifact — there's no "format" variant
to choose here. If we ever emit a different patch-management format (Jamf
Title Editor JSON, AutoPkg recipe, etc.), it goes behind a dedicated endpoint
with its own response shape, not as a format toggle here.

``content`` is a structured object (Installomator variable name → value),
not a pre-rendered bash label string. Consumers compose the label from these
fields however they want — drop into a fragment file, pass to Installomator's
``valuesfromarguments`` mechanism, translate to another tool's format, etc.
Fields that couldn't be resolved are omitted from ``content``; their absence
is explained in ``warnings``.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class GenerateLabelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_name: str
    content: dict[str, Any]
    sources_used: list[str]
    warnings: list[str]
