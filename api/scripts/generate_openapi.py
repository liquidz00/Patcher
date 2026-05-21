"""
Dump the OpenAPI schema to docs/_generated/openapi.json.

Run before sphinx-build so the {openapi} directives in
``docs/api/endpoints.md`` have a fresh schema to render against.

The Makefile's ``docs`` target invokes this script automatically. Run it
by hand only when iterating on the API surface and you want to refresh
the generated artifact without a full docs rebuild.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "api"))

from patcher_api.main import app

OUT_PATH = REPO_ROOT / "docs" / "_generated" / "openapi.json"


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUT_PATH.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Wrote {OUT_PATH.relative_to(REPO_ROOT)} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
