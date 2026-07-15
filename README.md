# repo-walk

A Claude Code plugin that walks a GitHub repository's history **one step at a
time and narrates it** — not just listing commits/issues/PRs, but explaining
*why* each change happened, *what* it did, and *how* it builds on what came
before.

`git log` and `gh` already list history. This plugin is the part that
**explains** it — using Claude to turn a repo's evolution into a guided,
step-by-step read. Great for onboarding onto an unfamiliar codebase or studying
how a well-made project grew.

## How it works

It's a thin wrapper: `gh` fetches the data, Claude does the narration. No server,
no API keys, no database — just one slash command.

- **PR-centric by default** — a PR is the natural unit of understanding: the
  linked issue says *why*, the PR body says *what*, the commits inside say *how*.
  It walks merged PRs in chronological order.
- **`--timeline` mode** — pure chronological: interleaves commits, issues, and
  PRs on a single time axis (noisier on big repos, but that's the point of the mode).
- **Scoped by design** — nobody reads a kernel from commit #1. Defaults to the
  most recent 15 units; narrow with `--limit`, `--path`, `--since`.
- **Resumable** — progress is saved to a local cursor file, so you can walk a
  long history across several sittings with `... next`.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [`gh` CLI](https://cli.github.com/), authenticated (`gh auth login`)

## Install

```
/plugin marketplace add hyeongyu-data/repo-walk
/plugin install repo-walk
```

Or clone and point Claude Code at the directory.

## Usage

```
/repo-walk owner/repo                     # PR-centric walk, recent 15 PRs
/repo-walk owner/repo --timeline          # pure chronological (commits+issues+PRs)
/repo-walk owner/repo --path src/auth     # only history touching a path
/repo-walk owner/repo --since 2024-01-01  # only recent history
/repo-walk owner/repo --limit 40 --batch 5
/repo-walk owner/repo next                # continue from where you left off
/repo-walk owner/repo reset               # start over
```

While walking, you can also just ask things like *"show me the diff for #123"* or
*"why was this needed?"* — Claude has the context loaded.

## What it deliberately does NOT do

Kept lazy on purpose (add later only if actually needed):

- No full "walk every commit from #1" mode — it always works on a scoped slice.
- No custom auth / API-key management — it reuses your `gh` login.
- No web UI, graphs, or cross-repo dashboards.

## License

MIT
