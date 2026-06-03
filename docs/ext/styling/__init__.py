"""Presentational MyST directives for the Patcher docs.

Bundles the visual building blocks (``steps``, ``markers``, ``highlights``,
``prompt``) behind one Sphinx extension. Each lives in its own submodule and
exposes a ``register(app)``; adding another is one more submodule plus a line
in :func:`setup`.
"""
from sphinx.application import Sphinx

from . import definition, highlights, markers, prompt, steps


def setup(app: Sphinx) -> dict[str, object]:
    """Sphinx extension setup. Registers every styling directive."""
    steps.register(app)
    markers.register(app)
    highlights.register(app)
    prompt.register(app)
    definition.register(app)
    return {"version": "0.3", "parallel_read_safe": True, "parallel_write_safe": True}
