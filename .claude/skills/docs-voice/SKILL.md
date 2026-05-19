---
name: docs-voice
description: |
  Review a Patcher documentation file (or glob) against the project's voice rules
  and propose rewrites that drop robotic patterns: "Patcher is designed to..."
  preambles, heading-restating lead paragraphs, hedged passive voice, jargon,
  diminishing language, and em-dashes. Defaults to report-only with suggested
  rewrites; switches to apply-mode only when the user explicitly says so.

  Invoke when the user says: "/docs-voice <path>", "voice check <path>", "rewrite
  voice in <path>", "audit voice in <path>", "fix tone in <path>", or similar.
  Path is the single required argument; can be a file (`docs/guides/export.md`) or
  a glob (`docs/guides/*.md`, `docs/**/*.md`).
---

# docs-voice

Patcher's docs sit in `docs/` as MyST markdown. They tend toward robotic patterns
that the user has explicitly flagged: lead paragraphs that restate the heading,
hedged passive voice, jargon that hides the user benefit, "Patcher is designed
to..." preambles, and em-dashes (a common AI tell). This skill reviews a target
file (or glob) against those rules and proposes rewrites.

## Required argument

A file path or glob, relative to the repo root or absolute. Examples:

- `docs/guides/export.md` - single file
- `docs/guides/*.md` - section
- `docs/**/*.md` - whole docs tree (use sparingly; output gets long)

Resolve the path before reading. If it doesn't exist, say so and stop.

## Modes

Two modes; default is **review**.

- **Review** (default): read the file, identify offenders, propose rewrites. Don't
  edit anything. Output is a per-file report (see Output below).
- **Apply**: rewrite in place. Only enter this mode if the user said one of: "apply",
  "rewrite", "fix", "do it", "go ahead". If unsure, stay in review mode and ask.

In apply mode, still surface the diff (before → after) for each change so the user
can spot bad rewrites. Edit one file at a time.

## Voice rules

Apply these in order. Each has an example before/after to anchor the rewrite.

### 1. Drop "Patcher is designed to..." / "Patcher provides..." preambles

These hedge the verb and bury the action.

- ❌ "Patcher is designed to run unattended: on a workstation via `launchd`..."
- ✅ "Run Patcher on a schedule via `launchd` or in CI/CD."

### 2. Drop heading-restating lead paragraphs

If the lead paragraph says what the H1/H2 already said, cut it or replace it with
the *why* the user is on this page.

- Heading: "Export"
  - ❌ "The `export` command (and `PatcherClient.export`) pulls patch management
    data from Jamf and writes reports to disk..."
  - ✅ "Fetch the latest patch data and write it in your chosen format."

### 3. Drop hedged passive voice

Phrases like "is designed to", "allows you to", "provides the ability to", and
"when something goes wrong" soften statements that should be direct.

- ❌ "Knowing what lives where makes it easier to inspect, reset, or relocate
  state when something goes wrong."
- ✅ "Know what lives where so you can debug, reset, or recover state."

### 4. Lead with user outcome, not implementation

The reader cares what they get, not what's underneath.

- ❌ "Patcher's `patcherctl` CLI and the importable `PatcherClient` library share
  a single credential model."
- ✅ "Set up credentials once; both the CLI and library use them."

### 5. Strip in-house jargon unless defined

Words like "cross-references", "surfaces", and "semantics" hide the user benefit.
Replace with plain verbs.

- ❌ "How Patcher cross-references Jamf software titles with Installomator's label
  catalog to surface automation-ready apps."
- ✅ "Which of your Jamf apps have Installomator labels, so you can automate them."

### 6. Drop diminishing language

Words like "small set", "tweaks", "just", "simply", and "basic" undersell the
feature and add no content.

- ❌ "Patcher's PDF and HTML reports support a small set of branding tweaks..."
- ✅ "Customize your PDF and HTML reports with company branding."

### 7. Drop "This page describes..." / "This section covers..." openers

- ❌ "This page describes how to configure SSO with Patcher."
- ✅ "Configure Patcher for SSO."

### 8. No em-dashes

Em-dashes (`—`, U+2014) read as an AI tell. Drop them from prose entirely. Use
parentheses, a semicolon, a period split, or a comma, depending on the rhythm.

- ❌ "The build is fast — typically under 30 seconds."
- ✅ "The build is fast. Typically under 30 seconds."
- ❌ "Pull patch data from Jamf — Excel, PDF, HTML, or JSON — and write to disk."
- ✅ "Pull patch data from Jamf (Excel, PDF, HTML, or JSON) and write to disk."

The only acceptable dash-like character in prose is the **hyphen** (`-`, U+002D)
used inside a bullet definition pattern. That's a hyphen, not an em-dash.

- ✅ `- **Subject** - One-line definition of the subject.`

If a file uses `--` (double-hyphen, which some markdown renderers turn into an
em-dash), flag it the same way and recommend the same replacements.

## Detection patterns (start here, then read for context)

`grep -nE` against the file is a useful pre-pass but not authoritative. False
positives are common, and the worst offenders aren't pattern-matchable. Use these
to seed the review, then read the surrounding paragraph:

```
^Patcher (is|provides|supports|allows|enables|offers)
^This (page|section|guide|document) (describes|covers|explains|outlines)
\b(is designed to|allows you to|provides the ability to|makes it (easy|easier|possible))\b
\b(simply|just|basic|small set of|tweaks)\b
\b(cross-?references?|surfaces?|semantics)\b
—
```

The last line is a literal em-dash (U+2014). Em-dash hits are usually real
offenders, not false positives.

Read every flagged line in context before proposing a rewrite. Don't blindly
substitute. A paragraph using "surface" as the verb is robotic; a code comment
using "surface" as a noun isn't.

## Output format

For each file reviewed, emit a block like this:

```
docs/guides/export.md
─────────────────────────────────────────────────────────────

L9  rule 2 (heading-restating) + rule 5 (jargon)
    before: The `export` command (and `PatcherClient.export`) pulls patch management
            data from Jamf and writes reports to disk...
    after:  Fetch the latest patch data and write it in your chosen format.

L24 rule 1 (preamble) + rule 3 (hedged passive)
    before: Patcher is designed to handle long-running exports gracefully...
    after:  Long-running exports run unattended. Cancel with Ctrl+C.

L40 rule 8 (em-dash)
    before: The export pipeline runs in batches — typically 5 at a time.
    after:  The export pipeline runs in batches (typically 5 at a time).

(3 offenders across 78 lines)
```

For glob targets, emit one block per file plus a summary line at the end:

```
Reviewed 7 files · 14 offenders · 5 files clean
```

If a file is clean, print:
```
docs/concepts/architecture.md - clean
```

## What this skill does NOT do

- Does not rewrite code blocks, admonition contents, or anything inside `{eval-rst}`
  or `:::` fenced blocks. Voice rules apply to prose only.
- Does not edit `CHANGELOG.md`, `README.md`, or `CLAUDE.md`. Those have different
  voice conventions (changelog terseness, contributor-facing tone). Scope is `docs/`.
- Does not touch frontmatter, toctree entries, or directive syntax.
- Does not propose structural changes (splits, merges, deletions). That belongs
  to the IA audit, not the voice pass.
- Does not enforce rules dogmatically. If a rule produces a worse sentence,
  flag it but keep the original. Note the conflict in the output.

## Edge cases

- **Lead-paragraph `{rst-class}` blocks**: Patcher uses `{rst-class} lead` for
  page-opener paragraphs styled larger. Apply the rules; the styling is orthogonal
  to the content.
- **API reference files (`docs/reference/*.rst`)**: skip these. They're autodoc
  shells with no prose to review. If the glob includes them, output:
  `docs/reference/foo.rst - skipped (autodoc-only)`.
- **MyST cross-references** (`{doc}`, `{ref}`, `{py:class}`): preserve verbatim
  in any rewrite.
- **Code snippets and tab-set blocks**: skip. Only review prose lines.
- **Em-dashes inside code blocks or URLs**: skip. Rule 8 applies to prose only.
