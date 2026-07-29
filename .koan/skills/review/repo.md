# This repository — identity and review scope

Facts about *this* repo that change how findings are judged. For review findings these
**supersede** the generic privacy wording in `KOAN.md` (priority 4, "the public tree must
not contain private operator identifiers") and in `CLAUDE.md` ("Never leak private
skill/agent/project names"). Both were written when this tree was a fork staged for the
public upstream. It no longer is.

## What this repo is

- **`webpros-sandbox/koan-bot`** — GitHub visibility **internal** (org-only, not public).
  This is the **definitive home** of the codebase, not a staging fork; changes are not
  contributed back to the public upstream.
- Every reader is already inside the WebPros trust boundary. An identifier naming this
  org, this repo, its issues/PRs, or its CI runner group is a self-reference, not a
  disclosure.

## Do NOT report identifier "privacy leaks"

This finding category is **retired for this repo**. Do not open a finding — at any
severity, including suggestion-only — because added lines contain:

- this repo, org, or their issue/PR numbers (`webpros-sandbox/koan-bot#1`, `Fixes #1`,
  `webpros-sandbox` as a runner group);
- any other org, repo, project, or product name;
- tracker key prefixes or concrete case numbers (`PREFIX-12345`);
- skill, slash-command, agent, or bot handle names.

Citing the issue a change fixes is **wanted** — in code comments, test docstrings,
`specs/**`, and commit messages alike. It is how this repo already cites prior work
(`PR #2309`, `#2455`, `#2466`), and `webpros` already appears across
`.github/workflows/` and `docs/operations/ci-runners.md` on `main`.

## What is still in scope

- **Hardcoded secrets** — tokens, API keys, passwords, credentials, URLs with embedded
  auth. Unchanged: still critical.
- **End-user PII** — real customer names, emails, or account IDs pasted into code,
  tests, or fixtures.
- Everything else in `quality-gates.md`.

If a finding's only harm is "this name identifies someone", drop it. If it discloses a
**credential** or **someone's personal data**, report it.
