# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys
from pathlib import Path

from src.patcher.__about__ import __version__

sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../src"))
sys.path.append(str(Path(".").resolve()))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Patcher"
copyright = "2024, Andrew Speciale & Chris Ball"
author = "Andrew Speciale & Chris Ball"

version = __version__
release = f"v{__version__}"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "sphinx.ext.autosummary",
    "sphinx.ext.autosectionlabel",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_copybutton",
]

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

# -- Options for copy button  ------------------------------------------------
# https://sphinx-copybutton.readthedocs.io/en/latest/use.html
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_baseurl = "http://patcher.liquidzoo.io"
html_theme = "pydata_sphinx_theme"
html_logo = "_static/logo.svg"
html_favicon = "_static/logo.svg"
html_static_path = ["_static"]
html_title = "Patcher"

html_css_files = ["css/custom.css"]

html_theme_options = {
    "navbar_align": "left",
    "announcement": "https://raw.githubusercontent.com/liquidz00/Patcher/main/docs/_templates/custom-template.html",
    "show_prev_next": False,
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
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
    "footer_center": ["sphinx-version"],
    "footer_end": ["theme-version"],
    "pygments_light_style": "github-light",
    "pygments_dark_style": "github-dark",
}

# Remove ethical ads from the sidebar
html_sidebars = {
    "contributing/index": [],
}

html_context = {
    "default_mode": "auto",
    "navbar_links": [
        ("Getting Started", "getting_started/index.html"),
        ("User Guide", "user/index.html"),
        ("Reference", "reference/index.html"),
        ("Contributing", "contributing/index.html"),
    ],
}
