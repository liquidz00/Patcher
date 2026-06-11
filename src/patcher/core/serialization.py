"""Conversions between ``PatchTitle`` objects and their DataFrame / dict representations."""

from datetime import datetime, timezone

import pandas as pd
from pydantic import ValidationError

from .models.patch import PatchTitle


def titles_to_df(titles: list[PatchTitle]) -> pd.DataFrame:
    """
    Build a DataFrame from ``PatchTitle`` objects.

    Columns are the model's snake_case field names. Callers that render reports
    re-case the columns for display; the diff path keeps them as-is.
    """
    return pd.DataFrame([title.model_dump() for title in titles])


def df_to_titles(df: pd.DataFrame) -> tuple[list[PatchTitle], list[str]]:
    """
    Build ``PatchTitle`` objects from DataFrame rows.

    Column labels are normalized back to snake_case before validation. Returns
    the parsed titles alongside an error message for each row that failed to
    validate, leaving the decision of how to report them to the caller.
    """
    titles: list[PatchTitle] = []
    errors: list[str] = []
    for _, row in df.iterrows():
        try:
            normalized = {str(key).lower().replace(" ", "_"): value for key, value in row.items()}
            titles.append(PatchTitle(**normalized))
        except (KeyError, ValueError, TypeError, ValidationError) as e:
            errors.append(f"{type(e).__name__}: {e}")
    return titles, errors


def titles_to_dict(titles: list[PatchTitle], report_title: str | None = None) -> dict:
    """
    Convert ``PatchTitle`` objects into a JSON-serializable envelope.

    The envelope has the shape::

        {
            "generated_at": "2026-05-04T18:30:00+00:00",
            "report_title": "...",
            "title_count": 42,
            "titles": [<PatchTitle.model_dump(mode="json")>, ...]
        }

    Internal keys (``title_id``, ``name_id``) are retained because JSON is a
    machine-to-machine transport; the human-facing PDF/Excel exports drop them
    via :data:`~patcher.policy.IGNORED_EXPORT_COLUMNS`.
    """
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_title": report_title,
        "title_count": len(titles),
        "titles": [title.model_dump(mode="json") for title in titles],
    }
