"""Pygments tweak so shell blocks read consistently.

A bash CLI invocation has almost nothing Pygments recognizes as syntax, so a
command like ``patcherctl`` renders plain and the leading ``$`` prompt is
unstyled, which makes shell blocks look inconsistent block to block. This
subclass of the bash lexer:

  - tags a line-leading ``$`` as ``Generic.Prompt`` so custom.css can style it, and
  - tags a known CLI in *command position* as ``Name.Builtin`` so it picks up the
    theme's builtin color.

"Command position" means the first word of a command line (after an optional
``$`` prompt). A known command only colors when it's actually the command, not
when it appears as an argument, so ``patcherctl`` colors in ``$ patcherctl export``
but not in ``$ pip install patcherctl``. Add a CLI by dropping it into ``COMMANDS``.

Registered for the ``bash`` highlight language, so every ```` ```bash ```` block
gets the same treatment with no per-block changes.
"""
from pygments.lexers.shell import BashLexer
from pygments.token import Generic, Name
from sphinx.application import Sphinx

# CLIs to color when they lead a command line. Extend as needed.
COMMANDS = frozenset({"patcherctl", "git", "uv", "pip", "gh", "python3", "/usr/libexec/PlistBuddy"})


class PatcherBashLexer(BashLexer):
    """Bash lexer that colors known CLIs in command position and the ``$`` prompt."""

    name = "PatcherBash"
    aliases = []  # bound to "bash" via add_lexer, not by alias resolution

    def get_tokens_unprocessed(self, text):
        at_command = True  # the next non-space word leads a command line
        for index, token, value in super().get_tokens_unprocessed(text):
            if value == "$" and (index == 0 or text[index - 1] == "\n"):
                token = Generic.Prompt
                at_command = True  # the command follows the prompt
            elif value.isspace():
                if "\n" in value:
                    at_command = True  # a new line starts a new command
            elif at_command:
                if value in COMMANDS:
                    token = Name.Builtin
                at_command = False  # only the first word is the command
            else:
                at_command = False
            yield index, token, value


def setup(app: Sphinx) -> dict[str, object]:
    """Register the lexer as the handler for ``bash`` code blocks."""
    app.add_lexer("bash", PatcherBashLexer)
    return {"version": "0.2", "parallel_read_safe": True, "parallel_write_safe": True}
