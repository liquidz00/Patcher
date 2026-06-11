"""
SQLAlchemy ORM models for the Patcher API.

Importing this package registers every model on ``Base.metadata``, which
Alembic's autogenerate (``alembic/env.py``) and the test suite's ``create_all``
rely on to see every table regardless of which module triggered it.
"""

from patcher_api.models import (  # noqa: F401
    app,
    autopkg,
    homebrew,
    installomator,
    jamf,
    mas,
)
