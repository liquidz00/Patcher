# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys

from src.patcher.__about__ import __version__

sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../src"))

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
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx.ext.autosummary",
    "sphinx.ext.autosectionlabel",
    "sphinxcontrib.autodoc_pydantic",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

add_module_names = False
autodoc_typehints = "both"
autodoc_member_order = "bysource"
autosectionlabel_prefix_document = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_title = f"Patcher {release}"

html_theme_options = {
    "navbar_align": "left",
    "show_prev_next": False,
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["navbar-icon-links"],
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
}

# Remove ethical ads from the sidebar
html_sidebars = {"**": ["sidebar-nav-bs"]}  # Removed 'sidebar-ethical-ads'

html_context = {
    "navbar_links": [
        ("Getting Started", "getting_started/index.html"),
        ("Reference", "reference/index.html"),
        ("Contributing", "contributing/index.html"),
    ]
}
