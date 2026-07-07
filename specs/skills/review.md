---
type: skill-spec
title: "Skill Spec — review"
tags: [skill]
created: 2026-06-27
updated: 2026-07-06
---

# Skill Spec — `review`

## Command(s)

- **Primary:** `/review [--now] <pr-or-issue-url> [more urls] [context] [flags]`
  or `/review <repo-url> [--limit=N]`
- **Aliases:** `rv`
- **Group:** `code`

## Purpose

Queue a code-review mission for one or more GitHub PRs/issues. The agent reviews the
diff and posts findings as a review comment. The default review can be sharpened with
focus passes (architecture, silent-failure hunting, comment quality, plan alignment).

See `docs/users/skills.md` for the end-user `/review` reference and
`docs/users/user-manual.md` for the fuller walkthrough.

## Inputs

| Input | Source | Required | Notes |
|---|---|---|---|
| PR/issue URL(s) | command arg | yes (or repo URL) | multiple allowed; parsed by `github_url_parser` |
| repo URL + `--limit=N` | command arg | alt form | batch-review N open PRs |
| `--now` | flag | no | queue at top |
| `--architecture` | flag | no | SOLID/layering focus |
| `--errors` | flag | no | silent-failure-hunter pass |
| `--comments` | flag | no | comment-quality pass |
| `--plan-url <issue-url>` | flag | no | check PR against its plan |
| `--force` | flag | no | review even if closed/merged |
| trailing context | command arg | no | extra reviewer guidance |

## Outputs / side effects

- Queues a review mission (one per URL); the agent loop runs it.
- Posts a review comment to the PR with a branded footer (`pr_footer.py`).
- Review prompt is enriched with `{ISSUE_CONTEXT}` from `issue_tracker/enrichment.py`.

## Error cases

| Condition | Behavior |
|---|---|
| invalid/missing URL | reply with usage |
| closed/merged target | skipped unless `--force` |
| unresolved project | alias resolution then skip if unknown |

## Integration hooks

- **Handler:** `handler.py`. **GitHub:** `github_enabled` + `github_context_aware`.
- **Combo member:** part of `review_rebase` (`/rr`) and `ultrareview`.
- **Async:** runs as a queued agent-loop mission.

## Diff budget pipeline

The diff the reviewing agent sees is produced by a fixed reduction chain; every
stage must preserve the ones after it or source files silently vanish from the
review (the failure mode that motivated this contract):

1. **Fetch** — `rebase_pr.fetch_pr_context(max_diff_chars=...)`. Review paths
   pass `REVIEW_DIFF_FETCH_MAX_CHARS` (280k chars ≈ the compressor's 80k-token
   budget, `constants.py`) when `optimizations.review_compressor` is enabled
   (default), else the conservative `PR_CONTEXT_DIFF_MAX_CHARS` (32k) since
   nothing downstream would bound the prompt. The fetch-time cap keeps whole
   file blocks in git's lexicographic order — it is a safety net, **not** the
   sizing mechanism.
2. **Ignore filters** — `review_ignore` glob/regex config (`utils.filter_diff_by_ignore`).
3. **Content triage** — `review_triage` config (`diff_triage.py`): lockfiles,
   generated files, whitespace-only, rename-only. Default off.
4. **Compression** — `diff_compressor.compress_diff` (80k-token budget,
   language-priority order: source > scripts > markup > data/lockfiles) runs in
   `review_runner._apply_review_diff_filters`, which stamps
   `compressor_skipped_files` on the context (present even when empty — the
   "already compressed" sentinel for `build_review_prompt`'s fallback path).
   Skipped files are surfaced to the agent in a prompt note.

Secondary passes get bounded slices of the *compressed* (priority-ordered)
diff: reflection `REVIEW_REFLECT_DIFF_MAX_CHARS` (32k chars), bot-comment
triage 12k; the silent-failure hunter gets the full compressed diff (capping
it would re-introduce the dropped-files bug for that pass).

**Invariant:** the fetch budget must be ≥ the compressor budget whenever the
compressor is enabled — otherwise the compressor is dead code and file
selection degrades to lexicographic order.

## Invariants

- Multi-URL queues preserve order via a single atomic locked insert.
- Findings are advisory comments — `/review` never merges or pushes code.
- **Verdict follows severity, not vibes.** `lgtm` (the merge verdict that drives
  the GitHub APPROVE / request-changes) is `true` whenever no `critical` or
  `warning` finding exists. `suggestion`-only findings are non-blocking — a PR
  with only nits is merge-ready and must NOT be rejected. `lgtm: false` requires
  at least one `critical`/`warning`. If a concern truly blocks merge, it is not a
  `suggestion`; promote it before blocking. This mirrors the code-level fallback
  in `_normalize_review_data` (`blocking iff any critical/warning`) and the
  verdict body builder's definition of "blockers".
- **Re-review comment handling:** on a re-review (new commits or a re-requested
  review) the bot posts a *fresh* summary comment (GitHub does not notify on
  edits). By default it first collapses the prior review comment to a short
  "superseded" pointer (`_collapse_old_review`). `review_history.preserve_previous`
  (global `config.yaml`, overridable per-project in `projects.yaml`, default
  `false`, fail-closed to `false`) skips that collapse so the prior review is
  left intact alongside the new one. Either way a fresh comment is posted.

## Evaluation

The review skill is the first skill covered by the deterministic eval harness
(`koan/app/skill_evals.py`; design in `specs/002-review-skill-evals/`).

- **Golden dataset:** `koan/skills/core/review/evals/cases/*.json` — seeded-bug
  cases (`sql_injection`, `bare_except`, `hardcoded_secret`) that must produce a
  finding at the right severity, precision cases (`clean_refactor`,
  `benign_style`) that must LGTM without false positives, and `suggestion_only`,
  which carries a legitimate low-severity nit that must be surfaced *and* still
  yield `lgtm: true` (guards the verdict-follows-severity invariant).
- **Scored dimensions:** JSON/schema validity (via `validate_review`), recall of
  seeded findings (file + keyword-stem + severity-band match), LGTM correctness,
  and precision (no flags on `forbidden_files`).
- **CI:** the offline scorer + dataset-validity tests run in the `fast` group on
  every PR — they never call the Claude subprocess.
- **Live:** `KOAN_EVAL_LIVE=1 python -m app.skill_evals review --live` invokes
  the real review pipeline over the dataset and compares against
  `evals/baseline.json`; run this before/after a prompt change to confirm an
  improvement (or catch a regression, which exits non-zero).

**Contract:** changing the review output schema (`review_schema.py`) or the
prompt (`review.md`) MUST be reflected in the golden cases / baseline so the eval
keeps measuring real behaviour.

## Known debt / watch-outs

- Focus flags compose; stacking many passes multiplies token cost.
- Plan-alignment (`--plan-url`) depends on the tracker being reachable.
