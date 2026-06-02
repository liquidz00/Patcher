"""Borderless card-strip directive (``highlights``).

Lays its content out as a horizontal row of borderless, accent-topped cards.
Two authoring forms are supported:

Definition list (icon + title + body per card)::

    ::::{highlights}
    {iconify}`octicon:terminal-16` Outside Python
    : You want catalog data from a shell script or a one-off curl.

    {iconify}`octicon:package-16` Catalog lookups
    : Current version, download URL, or source coverage for an app.
    ::::

Plain bullet list (body-only cards)::

    ::::{highlights}
    - First point.
    - Second point.
    ::::

The directive rewrites each definition-list term/definition pair into a single
card container so the title and body group together (a raw deflist renders them
as separate siblings, which cannot be styled as one card). A plain bullet list
passes through untouched and is styled by CSS.

Only the plural ``highlights`` container is registered; the singular
``highlight`` is a built-in Sphinx directive and must not be overridden.
"""

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective


class HighlightsDirective(SphinxDirective):
    """Render bullet-list or definition-list content as a borderless card strip."""

    has_content = True

    def run(self) -> list[nodes.Node]:
        scratch = nodes.container()
        self.state.nested_parse(self.content, self.content_offset, scratch)

        container = nodes.container(classes=["highlights"])
        for child in scratch.children:
            if isinstance(child, nodes.definition_list):
                for item in child.children:
                    if isinstance(item, nodes.definition_list_item):
                        container += self._card_from_item(item)
            else:
                # Plain bullet list (or anything else) passes through; CSS styles it.
                container += child
        return [container]

    @staticmethod
    def _card_from_item(item: nodes.definition_list_item) -> nodes.container:
        """Fold one term/definition pair into a single card with a styled title."""
        card = nodes.container(classes=["point"])
        title = nodes.paragraph(classes=["point-title"])
        body: list[nodes.Node] = []
        for sub in item.children:
            if isinstance(sub, nodes.term):
                title += sub.children
            elif isinstance(sub, nodes.definition):
                body = list(sub.children)
        card += title
        card += body
        return card


def register(app: Sphinx) -> None:
    """Register the highlights directive."""
    app.add_directive("highlights", HighlightsDirective)
