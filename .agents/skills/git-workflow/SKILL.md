---
name: git-workflow
description: Use when preparing, reviewing, committing, branching, or pushing changes in the fahmm repository. Enforces the repository's Conventional Commits and feature-branch workflow.
metadata:
  version: 1.0.0
---

# fahmm Git workflow

Use this skill for Git operations in this repository. Read [`CONTRIBUTING.md`](../../../CONTRIBUTING.md) if the repository rules or branch state are unclear.

## Branch rules

- Never commit directly to or push `main`.
- Start work from an up-to-date `main` and use a topic branch. Codex-created branches use `codex/<short-topic>`; other contributors may use `feature/<topic>`, `fix/<topic>`, or `docs/<topic>`.
- Push only the current topic branch. Do not force-push or rewrite history that may already be shared.
- The repository hooks in `.githooks/` reject non-Conventional-Commit headers and pushes targeting `main`. Enable them once with `git config core.hooksPath .githooks` if they are not active.
- Do not merge into `main`, change GitHub branch protection, or create/merge a pull request unless the user explicitly asks.
- Before switching branches, inspect `git status`; preserve all existing user changes and avoid reset, clean, checkout-overwrite, or rebase operations that could discard them.

## Commit messages

Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>[optional scope][!]: <short description>

[optional body]

[optional footers]
```

- Use lowercase types such as `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`.
- Use a short noun scope when useful, for example `feat(desktop): add meeting library`.
- Use `!` before `:` or a `BREAKING CHANGE: ...` footer for breaking changes.
- Keep unrelated changes in separate commits when practical. Do not amend an existing commit unless the user asks.

## Before commit or push

1. Check the current branch, upstream, and `git status`.
2. Review the complete staged diff. Stage only files that belong to the requested change; never include credentials, local meeting data, generated build output, or unrelated user edits.
3. Run the relevant checks when the user requests verification or when a repository gate requires them. Report checks that could not run.
4. Confirm the destination is a topic branch and the remote is the expected repository. Push with an explicit ref, for example `git push -u origin HEAD`.
5. Report the branch and commit SHA. Do not claim a pull request exists unless one was created at the user's request.
