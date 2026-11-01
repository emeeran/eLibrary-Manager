# .pipeline/purge/ — cleanup purge pen

Files the cleanup pipeline (`/cleanup-audit`, Phase 1) flagged as redundant,
orphaned, or superseded. **Nothing is deleted** — each was moved here with
`git mv` (mirroring its original path), so history is intact and every move is
reversible.

> **Why `.pipeline/purge/` and not `./trash2review/`?** The repo's `.gitignore`
> has broad unanchored `trash2review` rules (lines 23 & 25) covering a
> pre-existing *gitignored local reference dump* at the repo root (PRDs, plans,
> automation — ~109 files, intentionally untracked). Any path named
> `trash2review` is ignored, so a tracked pen can't live there. This pen is
> tracked and self-contained.

## Restore a file

```bash
git mv .pipeline/purge/<mirrored/path> <original/path>
```

Example — `docs/old.md` moved here as `.pipeline/purge/docs/old.md`:

```bash
git mv .pipeline/purge/docs/old.md docs/old.md
```

## Confirm deletion

Review each item. If you agree it's dead, `git rm` it. If it's load-bearing,
restore it (above) — that's a pipeline false positive; log the reason in
`AUDIT.md` / `.pipeline/purge-plan.md`.
