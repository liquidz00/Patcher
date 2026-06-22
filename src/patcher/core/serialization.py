"""Conversions between ``PatchTitle`` objects and their DataFrame / dict representations."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from .exceptions import PatcherError
from .models.patch import PatchTitle


def titles_to_df(titles: list[PatchTitle]) -> pd.DataFrame:
    """
    Build a DataFrame from ``PatchTitle`` objects.

    Columns are the model's snake_case field names. Callers that render reports
    re-case the columns for display; the diff path keeps them as-is. The nested
    ``sources`` map is stored as a JSON string so it survives the Parquet cache
    round-trip — Parquet can't write an empty struct column.
    """
    rows = []
    for title in titles:
        row = title.model_dump()
        row["sources"] = json.dumps(row.get("sources") or {})
        rows.append(row)
    return pd.DataFrame(rows)


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
            sources = normalized.get("sources")
            if isinstance(sources, str):  # JSON string from a Parquet snapshot
                normalized["sources"] = json.loads(sources) if sources else {}
            titles.append(PatchTitle(**normalized))
        except (KeyError, ValueError, TypeError, ValidationError) as e:
            errors.append(f"{type(e).__name__}: {e}")
    return titles, errors


def excel_to_titles(path: str | Path) -> list[PatchTitle]:
    """
    Hydrate ``PatchTitle`` objects from a previously-exported Patcher Excel report.

    Reverses :meth:`~patcher.core.exporter.Exporter.export`'s Excel shape: columns
    are Title-Cased and normalized back to snake_case by :func:`df_to_titles`, and
    ``completion_percent`` / ``total_hosts`` are recomputed by ``PatchTitle``'s
    validator. The export strips ``title_id`` (an internal id, see
    :data:`~patcher.policy.IGNORED_EXPORT_COLUMNS`), so a synthetic one is supplied
    here — ``analyze`` filters on metrics, not identifiers.

    :param path: Path to a Patcher-exported ``.xlsx`` report.
    :raises PatcherError: If the file can't be read, is empty, or yields no titles.
    """
    path = Path(path)
    if not path.is_file():
        raise PatcherError("Excel report is not a readable file.", path=str(path))
    if path.suffix.lower() not in (".xlsx", ".xls"):
        raise PatcherError("Expected an Excel (.xlsx/.xls) Patcher export.", path=str(path))
    try:
        # dtype=str so numeric-looking versions stay strings; the model coerces the numeric fields.
        df = pd.read_excel(path, dtype=str)
    except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
        raise PatcherError("Could not read the Excel report.", path=str(path), error_msg=str(e))

    if df.empty:
        raise PatcherError("The Excel report contained no rows.", path=str(path))

    df = df.where(pd.notna(df), None)  # NaN -> None for optional/missing fields
    if not any(str(col).strip().lower().replace(" ", "_") == "title_id" for col in df.columns):
        df["title_id"] = [str(i) for i in range(len(df))]

    titles, errors = df_to_titles(df)
    if not titles:
        raise PatcherError(
            "Could not read any patch titles from the Excel report. Is it a Patcher export?",
            path=str(path),
            error_msg="; ".join(errors[:3]) or "no rows hydrated",
        )
    return titles


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
