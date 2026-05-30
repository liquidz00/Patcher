"""
Custom Sphinx directive for styling AI prompts as chat input boxes.

Accepts a ``:type:`` option to mimic the visual style of specific AI
client interfaces (Claude Code, Claude Desktop, Cursor, ChatGPT) without
exact replication. See ``PromptDirective`` docstring for supported types.

Originally adapted from:
https://github.com/liquidz00/jamfmcp/blob/main/docs/_ext/ai_prompt.py
"""

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.application import Sphinx
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

logger = logging.getLogger(__name__)

# Recognized visual styles. Anything else (including the legacy "default",
# "cursor", and "chatgpt" values) falls back to ``claude-desktop`` with a
# warning so an author catches typos before the page renders unexpectedly.
_KNOWN_TYPES = frozenset({"claude-code", "claude-desktop"})
_DEFAULT_TYPE = "claude-desktop"


class prompt(nodes.General, nodes.Element):
    """Node for AI prompt boxes."""
    pass


def visit_prompt_html(self, node):
    """Generate opening HTML for an AI prompt, with a type-specific class."""
    text = node.astext()
    prompt_type = node.get("type", _DEFAULT_TYPE)
    self.body.append(
        f'<div class="ai-prompt-box ai-prompt-{prompt_type}">'
        f'<div class="ai-prompt-input">{self.encode(text)}</div>'
        f'</div>'
    )
    # Skip children — text is already rendered above.
    raise nodes.SkipNode


class PromptDirective(SphinxDirective):
    """
    Directive to create styled AI prompt input boxes.

    Usage in Markdown (MyST):
        :::{prompt}
        Get the latest Firefox version
        :::

        :::{prompt}
        :type: claude-code
        Show me drift in the catalog
        :::

    Supported ``:type:`` values:
        - ``claude-desktop`` (or omitted): mimics the Claude Desktop chat
          input — rounded rectangle with a ``+`` glyph bottom-left and a
          muted model indicator bottom-right. This is the default look.
        - ``claude-code``: terminal-style with horizontal divider lines,
          accent-colored ``❯`` prompt prefix, and a status bar below.

    An unknown ``:type:`` logs a build warning and falls back to
    ``claude-desktop``.
    """

    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        "type": directives.unchanged,
    }

    def run(self):
        node = prompt()
        prompt_type = self.options.get("type", _DEFAULT_TYPE).strip().lower()
        if prompt_type not in _KNOWN_TYPES:
            logger.warning(
                "Unknown prompt :type: %r; falling back to %r. "
                "Known types: %s.",
                prompt_type,
                _DEFAULT_TYPE,
                ", ".join(sorted(_KNOWN_TYPES)),
                location=(self.env.docname, self.lineno),
            )
            prompt_type = _DEFAULT_TYPE
        node["type"] = prompt_type

        text = "\n".join(self.content)
        node += nodes.Text(text)
        return [node]


def setup(app: Sphinx):
    """Register the extension with Sphinx."""

    # Add the node and directive
    app.add_node(
        prompt,
        html=(visit_prompt_html, None)  # No depart function needed
    )
    app.add_directive('prompt', PromptDirective)

    return {
        'version': '0.1.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
