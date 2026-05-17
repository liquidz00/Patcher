"""
SQLAlchemy ORM models for the Patcher API.

Importing this package registers every model on ``Base.metadata`` — used by
:func:`patcher_api.db.init_db` to make ``create_all`` see every table
regardless of which module triggered it.
"""

from patcher_api.models import app, homebrew, installomator, mas, token  # noqa: F401
