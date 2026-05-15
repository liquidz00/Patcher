# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import inspect
import os
import patcher
import sys
import warnings
from pathlib import Path

from sphinx.locale import _
from patcher.__about__ import __version__

sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../src"))
sys.path.insert(0, os.path.abspath("./ext"))
sys.path.append(str(Path(".").resolve()))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Patcher"
copyright = "Copyright &copy; 2026, Andrew Lerman & Chris Ball"
author = "Andrew Lerman & Chris Ball"

version = __version__
release = f"v{__version__}"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.linkcode",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_iconify",
    "sphinx_togglebutton",
    "myst_parser",
    "ghwiki",
    "styled_params",
]

# ghwiki
github_wiki_repos = {
    "Installomator": "https://github.com/Installomator/Installomator",
    "AutoPkg": "https://github.com/autopkg/autopkg",
}

github_wiki_default = "Installomator"

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Suppress specific warnings
suppress_warnings = [
    "autodoc",                # Suppress duplicate object warnings from autodoc
    "myst.xref_ambiguous",    # Suppress ambiguous cross-reference warnings
    "autosectionlabel.*",     # Suppress duplicate label warnings
]

# Autodoc options
add_module_names = False
autodoc_typehints = "both"
autodoc_member_order = "bysource"
autosectionlabel_prefix_document = True

toc_object_entries_show_parents = "hide"

# Pydantic options
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_field_summary = False

# MyST Options
myst_enable_extensions = [
    "colon_fence",
    "substitution",
    "attrs_block",
    "attrs_inline"
]

# Heading anchors
myst_heading_anchors = 4

# MyST Substitutions
myst_substitutions = {
    "version": __version__,
    "release": release,
}

# -- Link Code  --------------------------------------------------------------
# based on pandas doc/source/conf.py
def linkcode_resolve(domain, info):
    """Generate external links to source code on GitHub."""
    if domain != "py":
        return None

    modname = info.get("module")
    fullname = info.get("fullname")

    submod = sys.modules.get(modname)
    if submod is None:
        return None

    obj = submod
    for part in fullname.split("."):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                obj = getattr(obj, part)
        except AttributeError:
            return None

    try:
        fn = inspect.getsourcefile(inspect.unwrap(obj))
    except TypeError:
        try:  # property
            fn = inspect.getsourcefile(inspect.unwrap(obj.fget))
        except (AttributeError, TypeError):
            fn = None
    if not fn:
        return None

    try:
        source, lineno = inspect.getsourcelines(obj)
    except (TypeError, OSError):
        try:
            source, lineno = inspect.getsourcelines(obj.fget)  # property
        except (AttributeError, TypeError):
            lineno = None

    linespec = f"#L{lineno}-L{lineno + len(source) - 1}" if lineno else ""

    # Convert to relative path for GHlinks
    fn = os.path.relpath(fn, start=os.path.dirname(patcher.__file__))

    # If development version, link to `develop`
    branch_or_tag = "develop" if "dev" in __version__ else release

    return f"https://github.com/liquidz00/Patcher/blob/{branch_or_tag}/src/patcher/{fn}{linespec}"

# -- Options for copy button  ------------------------------------------------
# https://sphinx-copybutton.readthedocs.io/en/latest/use.html
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# -- sphinx_togglebutton options ---------------------------------------------
togglebutton_hint = str(_("Click to expand"))
togglebutton_hint_hide = str(_("Click to collapse"))

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_baseurl = "https://patcher.readthedocs.io"
html_theme = "shibuya"
html_logo = "_static/v2-logo.svg"
html_favicon = "_static/v2-logo-favicon.svg"
html_static_path = ["_static"]
html_title = f"{release}"

html_css_files = [
    "css/custom.css",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/css/all.min.css"
]

# -- RTD version awareness ---------------------------------------------------
# READTHEDOCS_VERSION_NAME is set by Read the Docs at build time (e.g. "latest",
# "develop", or a tag like "v2.4.0"). Used to pick a branch-appropriate banner
# and to feed the pydata-sphinx-theme version switcher.
rtd_version = os.environ.get("READTHEDOCS_VERSION_NAME", "")

if rtd_version == "develop":
    _announcement = (
        '<strong>You are reading the development docs.</strong> '
        'These cover unreleased changes on the <code>develop</code> branch. '
        '<a href="https://patcher.readthedocs.io/en/latest/">'
        'Switch to the latest stable docs &rarr;</a>'
    )
else:
    _announcement = (
        '<div class="sidebar-message"> '
        'Find us on the MacAdmins Slack! '
        '<a href="https://macadmins.slack.com/archives/C07EH1R7LB0">#patcher</a> '
        '</div>'
    )

html_theme_options = {
    # Shibuya-supported
    "color_mode": "auto",
    "dark_code": True,
    "announcement": _announcement,
    "light_logo": "_static/logo.svg",
    "dark_logo": "_static/logo-dark.svg",
    "open_in_chatgpt": True,
    "open_in_claude": True,
    "open_in_perplexity": True,
    "github_url": "https://github.com/liquidz00/Patcher",
    "slack_url": "https://macadmins.slack.com/archives/C07EH1R7LB0",
    "discussion_url": "https://github.com/liquidz00/Patcher/discussions",
    "nav_links": [
        {
            "title": "Changelog",
            "url": "https://github.com/liquidz00/Patcher/blob/main/CHANGELOG.md",
            "external": True,
        },
        {
            "title": "Resources",
            "children": [
                {
                    "title": "MacAdmins Foundation",
                    "url": "https://www.macadmins.org",
                },
                {
                    "title": "JamfNation",
                    "url": "https://community.jamf.com",
                },
                {
                    "title": "Jamf Pro Documentation",
                    "url": "https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Jamf_Pro_Documentation.html",
                },
            ]
        },
    ],
}

# Remove primary sidebar from contributing page
# TODO: Modify respective page metadata to hide sidebars instead
# html_sidebars = {
#     "contributing/index": [],
#     "macadmins/index": [],
# }

html_context = {
    "source_type": "github",
    "source_user": "liquidz00",
    "source_repo": "Patcher",
}
