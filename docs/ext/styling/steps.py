"""Numbered step-sequence directives (``steps`` / ``step``)."""
from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from ._shared import parse_inline


class StepsDirective(SphinxDirective):
    """Container for a numbered sequence of :rst:dir:`step` items."""

    has_content = True

    def run(self) -> list[nodes.Node]:
        container = nodes.container(classes=["steps"])
        self.state.nested_parse(self.content, self.content_offset, container)
        return [container]


class StepDirective(SphinxDirective):
    """A single step; the argument is the step title, the body is rich content."""

    has_content = True
    required_arguments = 1
    final_argument_whitespace = True

    def run(self) -> list[nodes.Node]:
        node = nodes.container(classes=["step"])
        title = nodes.paragraph(classes=["step-title"])
        title += parse_inline(self, self.arguments[0])
        node += title
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def register(app: Sphinx) -> None:
    """Register the steps directives."""
    app.add_directive("steps", StepsDirective)
    app.add_directive("step", StepDirective)
