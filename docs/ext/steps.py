"""Numbered step-sequence directives (``steps`` / ``step``)."""
from docutils import nodes
from docutils.statemachine import StringList
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective


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
        parsed = nodes.container()
        self.state.nested_parse(StringList([self.arguments[0]]), self.content_offset, parsed)
        if parsed.children and isinstance(parsed.children[0], nodes.paragraph):
            title += parsed.children[0].children
        else:
            title += nodes.Text(self.arguments[0])
        node += title
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def setup(app: Sphinx) -> dict[str, object]:
    """Sphinx extension setup."""
    app.add_directive("steps", StepsDirective)
    app.add_directive("step", StepDirective)
    return {"version": "0.1", "parallel_read_safe": True, "parallel_write_safe": True}
