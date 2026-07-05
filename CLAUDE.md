# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file Python script (`backup_github_repos.py`) that mirrors every GitHub repo the authenticated user can reach — owned, contributed-to, and organization repos — into a local directory. It clones repos that don't exist locally and `git pull --all`s ones that do, recursing into submodules in both cases.

## Running

```bash
pip install PyGithub                # only dependency
export GH_ACCSS_TKN=<personal_access_token>   # required; read from os.environ
python backup_github_repos.py                 # prompts to confirm path, backs up to default
python backup_github_repos.py -p /path/to/dir # custom backup root
python backup_github_repos.py -h              # help
```

There are no tests, linter config, or build step.

## Key behaviors to know

- **Auth is environment-only.** `GH_ACCSS_TKN` must be exported; `main()` reads it via `os.environ.get` and exits with a friendly message if it's unset. Cloning uses `repo.ssh_url`, so a working SSH key to GitHub is also required — the API token alone is not enough. Do not hard-code the token (see the warning comment at `main`).
- **Default path is hard-coded** to `/mnt/d/Sync/GitHub` (a WSL mount) as the argparse `-p/--path` default. Change the `default=` in `__main__` if working outside that environment.
- **Backup layout is derived from repo ownership**, not stored config. `classify_repo()` maps each repo to a subdirectory: `personal/` (owned by user), `<org_login>/` (owned by an org the user belongs to), or `contributed/` (others' repos the user contributes to); it returns `None` to skip a repo. For any repo the user doesn't own, membership is confirmed against `repo.get_contributors()` before backing it up — this is the main per-repo API cost.
- **Failures are per-repo and non-fatal.** The loop in `main()` wraps each repo in `try/except Exception`; a failing clone/update is appended to `exceptions` and reported at the end by `print_summary()` rather than aborting the run. `counts` is a dict keyed by category (`personal`, `contributed`, one entry per org login).
- **Git runs via `subprocess.run(..., check=True)`** with explicit `repo_path`/`cwd=` arguments — there is no `os.chdir`, so the process working directory stays put. A non-zero git exit raises `CalledProcessError`, which the per-repo handler catches.
- `parse_path()` returns `os.path.abspath(os.path.expanduser(path))`, so `~` and relative paths both work.
