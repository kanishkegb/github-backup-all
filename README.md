# GitHub Backup-All
A simple python code to backup up all repositories owned by user, user's organizations, and repositories owned by others which user has contributed. The code will clone new repositories if they do not exist in the local directory or pull new commits from GitHub if the repository already exists in the local directory. If a repository has submodules, they will be updated too.

What you just need to do is to run the code whenever you need to backup your GitHub repositories.

Backup will have the following structure:
```
+ GitHub
  + personal
    - repo_1
    - repo_2
  + contributed
    - repo_1
    - repo_2
  + organization_1
    - repo_1
    - repo_2
  + organization_2
    - repo_1
    - repo_2
```

## Setting-Up
  1. Create and activate a virtual environment, then install dependencies into it
  ```
  python3 -m venv .venv          # create the virtual environment
  source .venv/bin/activate     # on Windows: .venv\Scripts\activate
  pip install PyGithub          # GitHub API
  ```
  Activate the same environment (`source .venv/bin/activate`) in every new terminal before running the code.
  2. Create a [personal access token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) for GitHub. Copy the token and do the following in the terminal before running the code. You MUST to do this every time you run the code. You can skip this if you add the line to `~/.bashrc` or `~/.zshrc`.
  ```
  export GH_ACCSS_TKN=personal_access_token_generated_in_GitHub
  ```
  3. Make sure that you are connected to GitHub with an [ssh key](https://help.github.com/articles/connecting-to-github-with-ssh/).

## Backing-Up
Run the code:
```
python3 backup_github_repos.py
```

Repositories that are not yet on disk are always cloned. For repositories that
already exist locally, you are shown a numbered list and can pick which ones to
update — enter numbers and/or ranges (e.g. `1,3,5-8`), `all`, or `none`
(pressing Enter selects `all`). The prompt is skipped automatically when the
output is not a terminal (e.g. cron jobs).

### Arguments
- `-p`, `--path` — destination path for the backup.
- `-a`, `--all` (aliases `-y`, `--yes`) — update every existing repository
  without the interactive prompt.
- `--list-updated` — print only the names of repositories that received new
  commits, one per line, to stdout (implies `--all`; the run summary goes to
  stderr so stdout stays pipeable). For example:
  ```
  python3 backup_github_repos.py --list-updated > updated.txt
  ```
- `-n`, `--dry-run` — preview only. Reports which repositories *would* be
  cloned or updated without changing anything on disk. Existing repos are
  `git fetch`ed (which only updates remote-tracking refs — nothing is merged
  or checked out) and then compared against their upstream; missing repos are
  reported as "would clone". Combine with `--list-updated` to get just the
  names that would update on stdout. Note: a dry run still contacts GitHub and
  fetches each existing repo, so it is not instant on many repos — but it
  writes nothing you would have to undo.

While it runs, live progress is shown on stderr: a counter during the (slow)
discovery phase, and a per-repository line as each clone/update/check happens.

For help and arguments, run:
```
python3 backup_github_repos.py -h
```
