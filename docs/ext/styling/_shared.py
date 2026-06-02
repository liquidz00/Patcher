"""Shared helpers for the styling directives."""
from docutils import nodes
from docutils.statemachine import StringList


def parse_inline(directive, text):
    """Parse one line of inline markup (roles, emphasis, code) into inline nodes.

    Used for directive arguments and synthesized bits like an ``{iconify}`` icon,
    so a title or marker glyph can carry the same rich markup as body content.
    The wrapping paragraph docutils produces is stripped so the caller can drop
    the result straight into a title or bullet element.
    """
    scratch = nodes.container()
    directive.state.nested_parse(StringList([text]), directive.content_offset, scratch)
    if scratch.children and isinstance(scratch.children[0], nodes.paragraph):
        return list(scratch.children[0].children)
    return [nodes.Text(text)]
