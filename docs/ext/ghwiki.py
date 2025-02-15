import re
from typing import Dict, List, Optional, Tuple

from docutils import nodes
from docutils.nodes import Node, system_message
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util.docutils import SphinxRole


class GitHubWikiRole(SphinxRole):
    """Custom role to resolve GitHub Wiki references, supporting multiple repositories."""

    def process_link(self, repo_url: str, page_name: str, header: Optional[str] = None):
        page_slug = page_name.replace(" ", "-")

        if header:
            header_slug = self.format_header_anchor(header)
            return f"{repo_url}/wiki/{page_slug}#{header_slug}"

        return f"{repo_url}/wiki/{page_slug}"

    def format_header_anchor(self, header: str):
        """Format header text into GitHub-compatible anchor."""
        header_slug = header.strip().lower()
        header_slug = re.sub(r"[^\w\s-]", "", header_slug)  # Remove special chars
        return header_slug.replace(" ", "-")

    def parse_role_text(
        self, text: str, env: BuildEnvironment
    ) -> Tuple[Optional[str], str, str, Optional[str]]:
        """
        Parses the role text to extract optional link test, repository, page name, and header.
        Format: "Custom Link Text <Repo:Page#Header>"
        """
        link_text = None
        target_text = text.strip()

        if "<" in text and ">" in text:
            link_text, target_text = text.split("<", 1)
            link_text, target_text = link_text.strip(), target_text.strip(">")

        header_part = None
        page_part = target_text.strip()

        if "#" in target_text:
            page_part, header_part = target_text.split("#", 1)
            page_part, header_part = page_part.strip(), header_part.strip()

        if ":" in page_part:
            repo_name, page_name = page_part.split(":", 1)
            repo_name, page_name = repo_name.strip().lower(), page_name.strip()
        else:
            repo_name, page_name = env.config.github_wiki_default, page_part.strip()

        return link_text, repo_name, page_name, header_part

    def create_reference_node(
        self, link: str, link_text: str
    ) -> Tuple[List[Node], List[system_message]]:
        """Creates inline reference node for link."""
        ref_node = nodes.reference(rawsource=self.text, text=link_text, refuri=link)
        inline_node = nodes.inline()
        inline_node += ref_node
        return [inline_node], []

    def run(self) -> Tuple[List[Node], List[system_message]]:
        """Process custom role and generate appropriate reference node."""
        text = self.text
        env = self.inliner.document.settings.env

        repo_wikis = {k.lower(): v for k, v in env.config.github_wiki_repos.items()}

        link_text, repo_name, page_name, header_part = self.parse_role_text(text, env)
        repo_url = repo_wikis.get(repo_name)
        if not repo_url:
            return [
                self.inliner.reporter.warning(f"Unknown GitHub Wiki repository: {repo_name}")
            ], []

        link = self.process_link(repo_url, page_name, header_part)

        return self.create_reference_node(link, link_text or page_name)


def setup(app: Sphinx) -> Dict[str, object]:
    """Sphinx extension setup."""
    app.add_role("ghwiki", GitHubWikiRole())
    app.add_config_value("github_wiki_repos", {}, "env")
    app.add_config_value("github_wiki_default", None, "env")

    return {
        "version": "0.3",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
