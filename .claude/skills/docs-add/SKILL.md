---
name: docs-add
description: |
  Scaffold a new MyST documentation page for the Patcher docs site. Picks the
  right section by topic, generates a page that matches the project's existing
  template (target anchor, H1, `{rst-class} lead` paragraph, body), wires it
  into the section toctree in `docs/index.md`, and applies the project's voice
  rules from the start so a follow-up docs-voice pass isn't needed.

  Invoke when the user says: "/docs-add <topic>", "new docs page for <topic>",
  "scaffold a doc for <topic>", "add a usage page about <topic>", "draft a
  concept page on <topic>", or similar. Topic is required; section is optional
  (will be inferred or asked).
---

# docs-add

Patcher's docs live in `docs/` as MyST markdown, organized into six sections plus
a Reference subtree. This skill creates a new page in the right place with the
project's standard opening pattern, then updates `docs/index.md` to include it.

## Required argument

The topic of the new page. Examples:

- `"deploy on Linux with systemd"`
- `"writing a custom UI plist"`
- `"PatcherClient.fetch_patches signature"`

## Optional arguments

- **Section** - one of `getting-started`, `usage`, `concepts`, `api`, `support`,
  `reference`, or `roadmap`. If omitted, infer from the topic (see Section
  routing below) and confirm with the user before writing.
- **Slug** - the filename stem (e.g., `linux-systemd-deploy`). If omitted, derive
  from the topic by lowercasing, replacing spaces with `-`, and stripping
  punctuation. Confirm before writing if it might clash with an existing file.

## Section routing

| Section | Use for |
|---|---|
| `getting-started/` | First-time setup, install, initial credentials, customization out of the box. Reader is brand new. |
| `guides/` | Task-oriented how-to: "how do I X". CLI and library both shown via tab-sets. Reader knows the basics. |
| `concepts/` | Explanations of *how it works*: architecture, data flow, the Installomator matching strategy. Reader wants the mental model. |
| `api/` | The Patcher API service (FastAPI under `api/`). Endpoints, curl/Python examples, OpenAPI schema integration. |
| `support/` | FAQ, troubleshooting, known issues. Short entries, problem-first. |
| `reference/` | Module-by-module reference, mostly autodoc. Add new `.rst` files via the `reference/index.md` toctree. |
| `roadmap` | Single top-level page; only edit if the user explicitly says "roadmap". |

When the topic is ambiguous (e.g., "Installomator" could be `guides/`, `concepts/`,
or `getting-started/`), ask the user with a short choice list before writing.

## Page template

Every new page in `getting-started/`, `guides/`, or `concepts/` follows this shape:

```markdown
({SLUG})=

# {Title in sentence case}

:::{rst-class} lead
{One-sentence hook. Lead with the user outcome, not the implementation. ≤ 25 words.}
:::

{One short paragraph of orienting context. Why is the reader here? What will they
walk away with? Don't restate the H1.}

## {First section heading}

{Body.}
```

Notes on the template:

- **Target anchor** `({SLUG})=` - emitted for `getting-started/`, `guides/`, and
  `concepts/` pages so other docs can `{ref}` to them. Skip for `support/`, `api/`,
  and `reference/`.
- **Lead paragraph** - keep it ≤ 25 words. Burning that budget on "Patcher
  provides..." or "This page describes..." wastes the hook.
- **`{rst-class} lead`** - uses the colon-fence syntax already in use across the
  docs; matches the styled larger-text opener.

For `api/` pages, look at `docs/api/endpoints.md` as the template. For `support/`
pages, look at `docs/project/troubleshooting.md`.

For `reference/` pages (autodoc-only), follow the `.rst` pattern in
`docs/reference/jamf_client.rst` and friends. Keep them mechanical.

## Voice rules to apply while writing

Apply the project's voice rules from the start. These are the same rules
`docs-voice` enforces; better to bake them in than rewrite later.

1. Drop "Patcher is designed to..." / "Patcher provides..." preambles.
2. Don't restate the heading in the lead paragraph.
3. No hedged passive: "is designed to", "allows you to", "when something
   goes wrong".
4. Lead with user outcome, not implementation detail.
5. Strip jargon: replace "cross-references", "surfaces", "semantics" with
   plain verbs.
6. No diminishing language: "small set", "tweaks", "simply", "just", "basic".
7. No "This page describes..." / "This section covers..." openers.
8. **No em-dashes (`—`) in prose.** Use parens, semicolons, a period split, or
   a comma instead. The only acceptable dash-like character is a hyphen (`-`)
   inside a bullet-definition pattern like `- **Subject** - One-line definition.`

See the `docs-voice` skill for before/after examples.

## Toctree wiring

After writing the file, update the matching toctree in `docs/index.md`. Insert
the new entry in the logical position for that section (alphabetical isn't
required; read the existing order, since pages are typically ordered by reader
flow, not name).

Example: adding `guides/library-async.md` to the Usage section:

```diff
 ```{toctree}
 :caption: Usage
 :hidden:

 guides/export
 guides/analyze
 guides/reset
 guides/automation
 guides/library
+guides/library-async
 ```
```

For new pages in `reference/`, update `docs/reference/index.md` instead.

For `roadmap.md`, no toctree update is needed; it's a single top-level page
already wired.

## Workflow

1. Parse the topic argument. If it's terse (≤ 4 words), ask the user for a
   sentence describing what the page should cover.
2. Determine the section (route by topic, or ask).
3. Determine the slug (derive from topic, or ask).
4. Check for filename collisions: `ls docs/<section>/` and confirm the target
   doesn't exist.
5. Read the existing section index (or a representative page) to confirm the
   template pattern matches what's currently in use.
6. Write the new file using the template.
7. Update the toctree in `docs/index.md` (or `docs/reference/index.md`).
8. Report what was created and where it appears in the toctree.

## What this skill does NOT do

- Does not write the *content* of the page beyond the template scaffold. The
  user fills in the body, or asks Claude separately to draft body text once the
  scaffold exists. The skill's job is the page mechanics, not the prose.
- Does not run `make docs` or build the site. The user can verify locally.
- Does not delete or move existing pages. IA restructure is out of scope and
  belongs to a separate manual pass.
- Does not edit `CHANGELOG.md`, `README.md`, or `CLAUDE.md`.
- Does not generate `reference/*.rst` content; those are autodoc shells the
  user authors directly when adding new modules. The skill can scaffold the
  shell on request, nothing more.

## Edge cases

- **Topic is a question** ("how do I configure SSO?"): treat as a `guides/` page;
  rewrite the heading to imperative ("Configure SSO").
- **Section doesn't exist yet**: the user wants a new section. Don't create one
  silently. Flag it and ask whether they want to add a new toctree caption to
  `docs/index.md`.
- **Slug collides with existing file**: ask for a new slug; do not overwrite.
- **Page belongs in multiple sections**: pick the one the user is most likely
  reading from; cross-link from the others later.
