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
copyright = "2024, Andrew Lerman & Chris Ball"
author = "Andrew Lerman & Chris Ball"

version = __version__
release = f"v{__version__}"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.autosummary",
    "sphinx.ext.githubpages",
    "sphinx.ext.intersphinx",
    "sphinx.ext.linkcode",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_copybutton",
    "myst_parser",
    "sphinx_togglebutton",
    "ghwiki",
    "styled_params",
]

# ghwiki
github_wiki_repos = {
    "InstallomatorClient": "https://github.com/InstallomatorClient/InstallomatorClient",
    "AutoPkg": "https://github.com/autopkg/autopkg",
}

github_wiki_default = "InstallomatorClient"

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

default_role = "py:obj"

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Autodoc options
add_module_names = False
autodoc_typehints = "both"
autodoc_member_order = "bysource"
autosectionlabel_prefix_document = True

toc_object_entries_show_parents = "hide"

# Pydantic options
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_field_summary = False

# Add 'init' DocStrings to class DocStrings
autoclass_content = "both"

# MyST Options
myst_enable_extensions = ["colon_fence", "substitution", "attrs_block", "attrs_inline"]
myst_heading_anchors = 4

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
html_theme = "pydata_sphinx_theme"
html_logo = "_static/v2-logo.svg"
html_favicon = "_static/v2-logo-favicon.svg"
html_static_path = ["_static"]
html_title = f"{release}"

html_css_files = ["css/custom.css"]

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
        "https://raw.githubusercontent.com/liquidz00/Patcher/main/docs/_templates/custom-template.html"
    )

html_theme_options = {
    "external_links": [
        {"url": "https://github.com/liquidz00/Patcher/blob/main/CHANGELOG.md", "name": "Changelog"},
        {"url": "https://www.macadmins.org", "name": "MacAdmins Foundation"},
        {"url": "https://community.jamf.com", "name": "JamfNation"},
        {
            "url": "https://learn.jamf.com/en-US/bundle/jamf-pro-documentation-current/page/Jamf_Pro_Documentation.html",
            "name": "Jamf Pro Documentation",
        },
        {"url": "https://pypi.org/project/patcherctl", "name": "PyPi"},
    ],
    "header_links_before_dropdown": 3,
    "navbar_align": "left",
    "announcement": _announcement,
    "switcher": {
        "json_url": "https://patcher.readthedocs.io/en/latest/_static/switcher.json",
        "version_match": rtd_version or "latest",
    },
    # Don't fetch switcher.json at build time — RTD's develop build runs before
    # main has the file, which would otherwise produce a 404 warning and fail
    # the build under fail_on_warning. The browser validates at view time.
    "check_switcher": False,
    "show_prev_next": False,
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["version-switcher", "theme-switcher", "navbar-icon-links"],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/liquidz00/Patcher",
            "icon": "fab fa-github",
        },
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/patcherctl/",
            "icon": "fab fa-python",
        },
        {
            "name": "MacAdmins Slack",
            "url": "https://macadmins.slack.com/archives/C07EH1R7LB0",
            "icon": "fab fa-slack",
        },
    ],
    "logo": {
        "text": "Patcher",
        "image_dark": "_static/v2-logo-dark.svg",
    },
    "footer_start": ["copyright"],
    "footer_end": ["theme-version"],
    "back_to_top_button": False,
    "secondary_sidebar_items": {
        "**/*": ["page-toc", "sourcelink"],
    },
    "show_toc_level": 3,
    "pygments_light_style": "xcode",
    "pygments_dark_style": "github-dark",
}

# Remove primary sidebar from contributing page
html_sidebars = {
    "contributing/index": [],
    "macadmins/index": [],
}

html_context = {
    "default_mode": "auto",
    "navbar_links": [
        ("User Guide", "user/index.html"),
        ("Reference", "reference/index.html"),
        ("Contributing", "contributing/index.html"),
    ],
}
