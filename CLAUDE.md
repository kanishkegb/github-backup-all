# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file Python script (`backup_github_repos.py`) that mirrors every GitHub repo the authenticated user can reach — owned, contributed-to, and organization repos — into a local directory. It clones repos that don't exist locally and `git pull --all`s ones that do, recursing into submodules in both cases.

## Running

```bash
pip install PyGithub                # only dependency
export GH_ACCSS_TKN=<personal_access_token>   # required; read from os.environ
python backup_github_repos.py                 # confirm path, clone missing, pick which existing repos to update
python backup_github_repos.py -p /path/to/dir # custom backup root
python backup_github_repos.py -a              # update all existing repos, no prompt (also -y/--yes)
python backup_github_repos.py --list-updated  # print only names of repos with new commits (one per line, stdout)
python backup_github_repos.py -n              # dry run: report what would clone/update, change nothing (also --dry-run)
python backup_github_repos.py -h              # help
```

There are no tests or linter config checked in. Ad-hoc verification lives outside the repo (see "Testing without the dependency" below); there is no build step.

## Architecture

The file is split into an **engine** (does the work, no user interaction) and a thin **CLI layer** (prompts, prints, argparse), so a future GUI can drive the same engine.

- **`GitHubBackup` (engine class).** Constructed with `(token, dest_root)`; caches the `Github` client, the authenticated user, and org logins. `discover()` yields a `RepoTarget` per eligible repo; `process(target, out=, dry_run=)` clones or updates one repo (or, when `dry_run`, only fetches and reports) and returns a `RepoResult`. The `out` argument routes git's stdout (defaults to stderr; the CLI passes `subprocess.DEVNULL` in the quiet report modes). The engine never calls `input()`/`print()` (beyond what git itself emits).
- **`RepoTarget` / `RepoResult` dataclasses** are the interface between engine and callers. `RepoResult.status` is one of `cloned` / `updated` / `unchanged` / `skipped` / `failed`, plus `would-clone` / `would-update` in dry-run mode; the CLI (and later a GUI) interprets these instead of scraping printed output.
- **CLI layer** = `prompt_selection()`, `print_summary()`, `status()`, `run_backup()`, `main()`, and the `__main__` argparse block. `run_backup()` orchestrates: discover → split missing vs existing → clone all missing, update the selected existing → report. `status()` writes live progress to stderr (self-overwriting on a TTY, skipped on a non-TTY).

## Key behaviors to know

- **Auth is environment-only.** `GH_ACCSS_TKN` must be exported; `main()` reads it via `os.environ.get` and exits with a friendly message if it's unset. The client is built with `Github(auth=Auth.Token(token))` (the modern PyGithub API; the old positional `Github(token)` is deprecated). Cloning uses `repo.ssh_url`, so a working SSH key to GitHub is also required — the API token alone is not enough. Do not hard-code the token (see the warning comment at `main`).
- **Default path is hard-coded** to `/mnt/e/GitHub` (a WSL mount) as the argparse `-p/--path` default. Change the `default=` in `__main__` if working outside that environment.
- **Missing repos are always cloned; existing repos are opt-in.** `run_backup()` clones every repo not yet on disk, but existing clones are only pulled if selected. `prompt_selection()` shows a numbered menu parsed by `parse_selection()` (accepts `1,3,5-8`, `all`, `none`, Enter=all). When `--all`/`--list-updated`/`--dry-run` is set or `sys.stdin.isatty()` is false, it selects everything without prompting — so cron/pipes never block.
- **"Updated" means HEAD actually moved.** `update_repo()` records `git rev-parse HEAD` (`git_head()`) before and after `git pull --all` and returns whether it changed — this drives the `updated` vs `unchanged` status and the `--list-updated` output. Newly cloned repos are `cloned`, not `updated`.
- **`--dry-run` (`-n`) previews without mutating.** `check_repo()` runs `git fetch --all` (remote-tracking refs only — nothing merged or checked out) and counts `HEAD..@{u}` to decide `would-update` vs `unchanged`; missing repos become `would-clone`. Threaded via `process(..., dry_run=True)`. It still hits the GitHub API (discovery) and fetches each existing repo, so it is not free — but it writes nothing to disk. No upstream / detached HEAD → treated as `unchanged`.
- **stdout vs stderr split.** In `--list-updated` mode, only updated (or, under `--dry-run`, would-update) repo names go to **stdout** (one per line, pipeable); the summary, menu, and all `status()` progress go to **stderr**. In the report modes (`--list-updated`/`--dry-run`) git's own stdout is sent to `subprocess.DEVNULL` so noise like "Already up to date." never leaks. Keep this separation when editing output.
- **Backup layout is derived from repo ownership**, not stored config. `classify_repo()` maps each repo to a subdirectory: `personal/` (owned by user), `<org_login>/` (owned by an org the user belongs to), or `contributed/` (others' repos the user contributes to); it returns `None` to skip a repo. For any repo the user doesn't own, membership is confirmed against `repo.get_contributors()` before backing it up — this is the main per-repo API cost.
- **Failures are per-repo and non-fatal.** `GitHubBackup.process()` wraps each repo in `try/except Exception` and returns a `failed` `RepoResult` with the error text rather than raising, so one bad repo never aborts the run; `print_summary()` lists them at the end.
- **Git runs via `subprocess.run(..., check=True)`** with explicit `repo_path`/`cwd=` arguments — there is no `os.chdir`, so the process working directory stays put. A non-zero git exit raises `CalledProcessError`, caught per-repo in `process()`.
- `parse_path()` returns `os.path.abspath(os.path.expanduser(path))`, so `~` and relative paths both work.

## Python Environment

This project uses a virtual environment located at `.venv/`. 
Do NOT use `source .venv/bin/activate`.
Instead, invoke the interpreter and tools directly:
- Run Python: `.venv/bin/python <script>`
- Install packages: `.venv/bin/pip install <package>`
- Run tests/tools: `.venv/bin/pytest` or `.venv/bin/ruff`