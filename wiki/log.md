# Wiki Log

Append-only chronological record of operations on the wiki. Each entry begins with `## [YYYY-MM-DD] <op> | <description>` so it's parseable with `grep "^## \[" log.md | tail -N`.

Operations:
- `ingest` — not used in this wiki (no raw-source-compilation layer); see `SCHEMA.md` "Workflow customizations". Docs/specs are created/updated directly per the existing `CLAUDE.md` discipline.
- `query` — a question was answered against the wiki (typically only logged when the answer was filed back as synthesis).
- `lint` — a health check was run.
- `schema` — the schema was modified.
- `shard` — an index was sharded.
- `status` — a `specs/<NNN-slug>/` feature's computed status changed (draft → in-progress → shipped).

---

## [2026-07-04] schema | Bootstrapped LLM Wiki tooling (praneybehl/llm-wiki-plugin) spanning docs/ and the durable half of specs/ (specs/components, specs/skills): added wiki/SCHEMA.md documenting conventions and resolving the long-standing TODO(SPECS_DIR_COLLISION) between koan's own specs/ and speckit's per-feature folders, backfilled YAML frontmatter onto 77 pre-existing pages (56 docs, 8 component-specs, 12 skill-specs, specs/README.md), built wiki/index.md (including computed draft/in-progress status for the 3 active speckit feature folders), and set up wiki/docs, wiki/specs-components, wiki/specs-skills symlinks.

## [2026-07-04] lint | Ran the bundled wiki_lint.py/wiki_stats.py directly (plugin not yet installed via marketplace) and found they report 0 pages — Path.rglob() doesn't follow the wiki/docs, wiki/specs-components, wiki/specs-skills symlinks. Documented as a known limitation in SCHEMA.md (does not affect /wiki:query's index→page path or scripts/wiki_check.py, both of which read real paths directly). Performed a manual cross-link improvement pass instead: specs/components/core.md, agent-loop.md, bridge.md (previously zero docs/ references) now point to their matching docs/architecture/ pages; all 12 specs/skills/*.md now reference docs/users/skills.md + docs/users/user-manual.md; 7 of 8 docs/architecture/*.md pages now reference their matching specs/components/ page (docs/architecture/memory.md deliberately skipped — no genuine component-spec counterpart exists for the memory subsystem).

## [2026-07-06] update | Documented the review diff budget pipeline after fixing /review silently dropping source files: fetch_pr_context() gained a max_diff_chars param (default 32k; review paths pass a compressor-aligned 280k so diff_compressor's 80k-token priority budget is the real gate instead of dead code), compression moved into _apply_review_diff_filters (sentinel key compressor_skipped_files), and the reflection pass now gets a bounded 32k slice. Updated specs/skills/review.md (new "Diff budget pipeline" section), specs/components/git-github.md (fetch_pr_context contract row), and docs/architecture/github-and-trackers.md (new "Review Diff Budgets and Filters" section documenting review_ignore / review_triage / optimizations.review_compressor).
