"""Inline term-definition admonition (``definition``).

Defines a term where it's first introduced, so the docs don't need a standalone
glossary to maintain.

    :::{definition} slug
    A short, URL-safe identifier for an app in the catalog (e.g. `googlechrome`).
    :::

Renders as a Shibuya admonition titled "Definition: <term>". The term carries
inline markup, so `` `slug` `` or a role works. Styling (brand accent + bookmark
icon) lives in custom.css under `.admonition.definition`.
"""
from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from ._shared import parse_inline


class DefinitionDirective(SphinxDirective):
    """Admonition that defines a term. Argument is the term, body is the definition."""

    has_content = True
    required_arguments = 1
    final_argument_whitespace = True

    def run(self) -> list[nodes.Node]:
        node = nodes.admonition(classes=["definition"])
        title = nodes.title()
        title += nodes.Text("Definition: ")
        title += parse_inline(self, self.arguments[0])
        node += title
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def register(app: Sphinx) -> None:
    """Register the definition admonition."""
    app.add_directive("definition", DefinitionDirective)
