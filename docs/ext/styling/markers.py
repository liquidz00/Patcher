"""Unordered marker-list directives (``markers`` / ``marker``).

The visual sibling of ``steps``: the same vertical spine and circular markers,
but without numbering, for lists where order doesn't matter. Each marker's glyph
is an iconify icon, set per-marker with ``:icon:`` or defaulted on the container.

    ::::{markers}
    :icon: octicon:check-16

    :::{marker} Pure-shell pipelines
    Translate cleanly to native Python and resolve inline.
    :::

    :::{marker} macOS-userspace fragments
    :icon: octicon:skip-16
    Skipped here; the macOS runner picks them up in stage 2.
    :::
    ::::

Resolution order for a marker's glyph is item ``:icon:`` then the container's
``:icon:`` then ``_DEFAULT_ICON``. The container default is threaded down through
``env.temp_data`` while its content is parsed, then restored so nested ``markers``
blocks don't leak their default outward.
"""
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from ._shared import parse_inline

# Default glyph when neither the container nor the item sets :icon: (a filled dot).
_DEFAULT_ICON = "octicon:dot-fill-16"
# temp_data key carrying a container's default icon down to its child markers.
_ICON_KEY = "styling_marker_default_icon"


class MarkersDirective(SphinxDirective):
    """Container for a list of :rst:dir:`marker` items."""

    has_content = True
    option_spec = {"icon": directives.unchanged}

    def run(self) -> list[nodes.Node]:
        container = nodes.container(classes=["markers"])
        previous = self.env.temp_data.get(_ICON_KEY)
        self.env.temp_data[_ICON_KEY] = self.options.get("icon", _DEFAULT_ICON)
        self.state.nested_parse(self.content, self.content_offset, container)
        if previous is None:
            self.env.temp_data.pop(_ICON_KEY, None)
        else:
            self.env.temp_data[_ICON_KEY] = previous
        return [container]


class MarkerDirective(SphinxDirective):
    """A single marker; the argument is the title, the body is rich content."""

    has_content = True
    required_arguments = 1
    final_argument_whitespace = True
    option_spec = {"icon": directives.unchanged}

    def run(self) -> list[nodes.Node]:
        node = nodes.container(classes=["marker"])
        icon = self.options.get("icon") or self.env.temp_data.get(_ICON_KEY, _DEFAULT_ICON)

        bullet = nodes.container(classes=["marker-bullet"])
        bullet += parse_inline(self, f"{{iconify}}`{icon}`")
        node += bullet

        title = nodes.paragraph(classes=["marker-title"])
        title += parse_inline(self, self.arguments[0])
        node += title

        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def register(app: Sphinx) -> None:
    """Register the markers directives."""
    app.add_directive("markers", MarkersDirective)
    app.add_directive("marker", MarkerDirective)
