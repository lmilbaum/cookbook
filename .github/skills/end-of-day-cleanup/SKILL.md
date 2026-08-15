---
name: end-of-day-cleanup
description: 'Use when the user says "we are done for today" or asks to clean up the workspace at the end of a session. Remove disposable local artifacts, verify the repository, and summarize remaining changes without deleting project data or committing without permission.'
argument-hint: 'Optional cleanup scope or files to preserve'
user-invocable: true
disable-model-invocation: false
---

# End-of-Day Cleanup

Clean the workspace conservatively at the end of a session. The goal is to remove disposable artifacts and leave a clear, trustworthy repository state.

## Procedure

1. Inspect the repository before changing anything:
   - Run `git status --short --branch`.
   - Check for active background terminals or development servers.
   - List obvious generated files and temporary artifacts.
2. Never delete or modify these without explicit user approval:
   - `.env` files, API keys, tokens, passwords, or session files.
   - Stored post records, titles, recipe links, cached images, or reports.
   - Source files, configuration files, documentation, tests, lockfiles, or user edits.
   - Any tracked file, even if it appears old or unused.
3. Remove only disposable local artifacts when they are clearly safe:
   - Python `__pycache__/` directories and `*.pyc` files.
   - `.pytest_cache/`, `.ruff_cache/`, and similar tool caches.
   - Temporary files such as `*.tmp`, editor swap files, and failed atomic-write leftovers.
   - Stale backup files only after confirming they are not tracked and are not user data.
4. Do not run a scraper, fetch external data, rewrite reports, or alter the post store as part of cleanup.
5. Do not commit, push, reset, checkout, or discard user changes unless the user explicitly asks.
6. Validate after cleanup:
   - Run the narrowest available compile, test, or lint check for files affected by cleanup.
   - Run `git diff --check`.
   - Run `git status --short --branch` again.
7. Report:
   - What disposable artifacts were removed.
   - What was deliberately preserved.
   - Any running process that needs manual attention.
   - Whether the worktree is clean or has user changes.

## Safety Rules

- If a file could contain credentials, scraped data, or user-authored content, preserve it and ask before deleting it.
- If cleanup would change a tracked file, stop and ask for confirmation.
- Treat generated reports as user-facing data, not disposable cache, unless the user explicitly identifies them as temporary.
- Keep cleanup idempotent: running the skill twice should not change additional project content.
