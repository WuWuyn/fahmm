# Contributing

## Git workflow

- Do not commit directly to or push `main`. Work on a topic branch and open a pull request for review.
- Codex branches use `codex/<short-topic>`; contributors may also use `feature/`, `fix/`, or `docs/` prefixes.
- Use [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages. Format: `<type>[scope][!]: <description>`. Example: `feat(desktop): add meeting library`.
- Use `BREAKING CHANGE: ...` in a footer or `!` in the header for breaking changes.
- Never force-push or rewrite shared history. Keep commits focused and review the staged diff before committing.
- Do not commit secrets, recordings, meeting data, or generated build output.
- Run the checks relevant to the files changed and include their results in the pull request.
- Enable the repository hooks after cloning with `git config core.hooksPath .githooks`. The commit hook checks Conventional Commit headers; the push hook blocks pushes to `main`.

The matching agent instructions live in [`.agents/skills/git-workflow/SKILL.md`](.agents/skills/git-workflow/SKILL.md).

## Frontend design work

Use the repository-local [Impeccable skill](.agents/skills/impeccable/SKILL.md) for frontend design and review. It is installed with `impeccable install --project`; its upstream Apache-2.0 license is kept beside the skill.
