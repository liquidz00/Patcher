# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys
from pathlib import Path

from sphinx.locale import _
from src.patcher.__about__ import __version__

sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../src"))
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
    "sphinx.ext.viewcode",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_copybutton",
    "myst_parser",
    "sphinx_togglebutton",
]

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

# Pydantic options
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_field_summary = False

# Add 'init' DocStrings to class DocStrings
autoclass_content = "both"

# MyST Options
myst_enable_extensions = ["colon_fence", "substitution", "attrs_block", "attrs_inline"]
myst_heading_anchors = 4

# -- Options for copy button  ------------------------------------------------
# https://sphinx-copybutton.readthedocs.io/en/latest/use.html
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# -- sphinx_togglebutton options ---------------------------------------------
togglebutton_hint = str(_("Click to expand"))
togglebutton_hint_hide = str(_("Click to collapse"))

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_baseurl = "http://patcher.liquidzoo.io"
html_theme = "pydata_sphinx_theme"
html_logo = "_static/logo.svg"
html_favicon = "_static/logo.svg"
html_static_path = ["_static"]
html_title = f"{release}"

html_css_files = ["css/custom.css"]

html_theme_options = {
    "external_links": [
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
    "announcement": "https://raw.githubusercontent.com/liquidz00/Patcher/main/docs/_templates/custom-template.html",
    "show_prev_next": False,
    "navbar_start": ["navbar-logo", "version-switcher"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "switcher": {
        "json_url": "https://patcher.liquidzoo.io/en/main/_static/switcher.json",
        "version_match": "develop",
    },
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
    ],
    "logo": {
        "text": "Patcher",
        "image_dark": "_static/logo-dark.svg",
    },
    "footer_start": ["copyright"],
    "footer_end": ["theme-version"],
    "back_to_top_button": False,
    "secondary_sidebar_items": {
        "**/*": ["page-toc", "sourcelink"],
    },
    "show_toc_level": 3,
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
