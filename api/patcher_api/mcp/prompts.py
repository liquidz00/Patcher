"""
MCP prompts exposed to clients.

Prompts are reusable, parameterized message templates a user invokes directly
(many clients surface them as slash commands). Each one seeds a conversation
that drives the read-only catalog tools through a useful workflow, so a user
does not have to remember which tools to chain. Returning a plain string makes
it a single user message; the model then calls the tools named in the text.
"""

from patcher_api.mcp.server import mcp


@mcp.prompt
def audit_app_coverage(slug: str) -> str:
    """Audit Patcher catalog coverage for one app, by slug."""
    return (
        f"Audit the Patcher catalog coverage for the app '{slug}'. Work through "
        "these steps and report the findings plainly.\n\n"
        "1. Call `get_app` to fetch the canonical record (identity, current "
        "version, install method, download metadata).\n"
        "2. Call `get_app_sources` to see which upstream sources (Installomator, "
        "Homebrew Cask, AutoPkg, Jamf App Installer) actually carry data for it.\n"
        "3. Call `list_drift` and check whether this app appears, meaning its "
        "sources disagree on the latest version.\n\n"
        "Summarize: which sources cover the app, whether there is version drift "
        "and which source looks stuck, and whether an Installomator label can be "
        "generated. If coverage is thin or drift exists, call it out directly."
    )


@mcp.prompt
def find_label_for(app_name: str) -> str:
    """Find an app by name and generate an Installomator label for it."""
    return (
        f"Generate an Installomator label for '{app_name}'.\n\n"
        "1. Call `search_apps` with the name to find candidate slugs. If several "
        "match, pick the closest and say which one you chose and why.\n"
        "2. Call `generate_installomator_label` with that slug.\n\n"
        "Present the resulting label content, name which upstream sources "
        "contributed, and surface any warnings (for example a missing "
        "`expectedTeamID` on a Homebrew Cask only app) so the user knows what to "
        "double-check before deploying it."
    )


@mcp.prompt
def catalog_health_report() -> str:
    """Summarize overall catalog coverage and call out the weakest areas."""
    return (
        "Produce a short health report on the Patcher catalog.\n\n"
        "1. Call `get_catalog_summary` for the total app count and per-source "
        "coverage counts.\n"
        "2. Call `list_categories` for the install methods, sources, and vendors "
        "present.\n\n"
        "Report the total catalog size, rank the upstream sources by coverage, "
        "and call out the weakest-covered source as the clearest place to improve. "
        "Keep it to a few sentences; this is an orientation summary, not an "
        "exhaustive dump."
    )
