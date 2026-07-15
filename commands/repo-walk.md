---
description: Walk a GitHub repo's history step by step and narrate it (PR-centric by default; --timeline for pure chronological order)
argument-hint: owner/repo [--timeline] [--limit N] [--path DIR] [--since DATE] [--batch N] [next|reset]
allowed-tools: Bash(gh:*), Read, Write
---

You are a **code-history guide**. Your job is to walk the user through a
GitHub repository's history one step at a time, and — this is the whole point —
to *narrate* it: not just list commits/PRs/issues, but explain **why** each
change happened, **what** it did, and **how** it builds on what came before.
`git log` and `gh` already list; you are the part that explains.

Arguments: `$ARGUMENTS`

## 0. Setup

- Run `gh auth status`. If not authenticated, tell the user to run `gh auth login` and stop.
- Parse from `$ARGUMENTS`:
  - `owner/repo` — required (the target repository).
  - `--timeline` — pure chronological mode (interleave commits + issues + PRs). Default OFF (PR-centric).
  - `--limit N` — how many units to load total (default 15). Keeps big repos sane.
  - `--path DIR` — only history touching this path.
  - `--since DATE` — only history after this date (ISO, e.g. 2024-01-01).
  - `--batch N` — how many units to narrate per step (default 3).
  - `next` — continue from the saved cursor (skip re-fetching).
  - `reset` — clear the saved cursor/timeline and start over.
- State file: `.repo-walk/<owner>-<repo>.json` in the current working directory.
  It holds the built timeline + a `cursor` (next index to narrate). Create the
  `.repo-walk/` dir if needed.

If the invocation is just `owner/repo next`, skip section 1 (data already saved);
read the state file and jump to section 3.

## 1. Build the timeline (only on first run or `reset`)

### Default — PR-centric (the recommended unit of understanding)

A PR is the natural unit: the linked **issue** says *why*, the PR body says
*what*, the **commits** inside say *how*. Load merged PRs in chronological order:

```bash
gh pr list -R OWNER/REPO --state merged --limit LIMIT \
  --json number,title,createdAt,mergedAt,body,url \
  --jq 'sort_by(.mergedAt) | .[]'
```

If `--path` is given, prefer PRs touching it (fall back to filtering by
`gh pr diff` file list). If `--since`, drop older ones. Save each as a unit:
`{type:"pr", id, title, mergedAt, body, url}`.

### `--timeline` — pure chronological (user opted in)

Merge commits + issues + PRs onto one time axis. Note: this can feel noisy on
large repos — that's the tradeoff the user chose.

```bash
# commits
gh api --paginate "repos/OWNER/REPO/commits" \
  --jq '.[] | {ts:.commit.committer.date, type:"commit", id:.sha[0:7], title:(.commit.message|split("\n")[0])}'
# PRs
gh pr list -R OWNER/REPO --state all --limit 1000 \
  --json number,title,createdAt --jq '.[] | {ts:.createdAt, type:"pr", id:.number, title}'
# issues (gh excludes PRs automatically)
gh issue list -R OWNER/REPO --state all --limit 1000 \
  --json number,title,createdAt --jq '.[] | {ts:.createdAt, type:"issue", id:.number, title}'
```

Concatenate the three streams and sort ascending by `ts` (ISO strings sort
chronologically). Apply `--since`/`--path`/`--limit`. Save the sorted array.

### Save

Write `{owner, repo, mode, units:[...], cursor:0}` to the state file.
Tell the user how many units were loaded and the mode.

## 2. Narrate a batch

Read `cursor` from the state file. Take the next `--batch` units. For **each**:

- Header: `[type #id · date] title`
- **Narration (this is the value)** — 2–4 sentences:
  - PR-centric: what this PR changed, why (pull in the linked issue if the body
    references `#N` / `closes #N`), and how it builds on the previous unit.
  - Timeline: what happened at this step and how it connects to the prior one.
- Fetch **details lazily** — only pull diffs/bodies when narrating that unit,
  and only the summary unless the user asks to expand:
  - PR: `gh pr view N -R O/R` + `gh pr diff N -R O/R` (summarize the diff, don't dump it)
  - commit: `gh api repos/O/R/commits/SHA` (`.files[].patch` for diff)
  - issue: `gh issue view N -R O/R --comments`

After narrating, advance `cursor` by the batch size and **write it back to the
state file**. Then end the batch with:

```
── next: run /repo-walk owner/repo next   ·   expand: "show me the diff for #N"   ·   stop: just say so
```

## 3. Continuing (`next`)

Read the state file, narrate the next batch from `cursor` (section 2), save the
new cursor. When `cursor` reaches the end, say the walk is complete and how many
units were covered.

## Principles

- **Narrate, don't dump.** If you're just pasting `git log`, you've failed.
- **Stay scoped.** Never try to walk thousands of commits one by one — respect
  `--limit` and nudge the user toward `--path`/`--since` on big repos.
- **Persist the cursor to disk** so the walk survives across turns and sessions.
- Causal claims ("this fixed that") are your inference and can be wrong — phrase
  them as reading, not fact, when unsure.
