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
  1. Install dependencies
  ```
  pip install pygithub # GitHub API
  ```
  2. Create a [personal access token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) for GitHub. Copy the token and do the following in the terminal before running the code. You MUST to do this every time you run the code. You can skip this if you add the line to `~/.bashrc` or `~/.zshrc`.
  ```
  export GH_ACCSS_TKN=personal_access_token_generated_in_GitHub
  ```
  3. Make sure that you are connected to GitHub with an [ssh key](https://help.github.com/articles/connecting-to-github-with-ssh/).

## Backing-Up
Run the code:
```
python backup_github_repos.py
```

For help and arguments, run:
```
python backup_github_repos.py -h
```
