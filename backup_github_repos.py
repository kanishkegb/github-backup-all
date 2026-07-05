from github import Github

import argparse
import os
import subprocess
import sys


def parse_path(path):
    '''
    Normalize a user-supplied path into an absolute, OS-independent path.

    Expands a leading ``~`` to the user's home directory and resolves any
    relative components against the current working directory.

    Args:
        path: (str) path to be normalized

    Returns:
        (str) absolute, normalized path
    '''

    return os.path.abspath(os.path.expanduser(path))


def clone_repo(repo, repo_path):
    '''
    Clone a repository into ``repo_path`` and initialize its submodules.

    Args:
        repo: (github.Repository) repository to clone
        repo_path: (str) destination directory for the clone

    Returns:
        None

    Raises:
        subprocess.CalledProcessError: if ``git clone`` or the submodule
            update exits with a non-zero status.
    '''

    print(f'Cloning into {repo_path}')

    subprocess.run(['git', 'clone', repo.ssh_url, repo_path], check=True)
    if os.path.exists(os.path.join(repo_path, '.gitmodules')):
        subprocess.run(
            ['git', 'submodule', 'update', '--init'],
            cwd=repo_path, check=True)


def update_repo(repo_path):
    '''
    Pull the latest changes for an existing clone and refresh its submodules.

    Args:
        repo_path: (str) path to the existing local clone

    Returns:
        None

    Raises:
        subprocess.CalledProcessError: if ``git pull`` or the submodule
            update exits with a non-zero status.
    '''

    print(f'Updating {repo_path}')

    subprocess.run(['git', 'pull', '--all'], cwd=repo_path, check=True)
    if os.path.exists(os.path.join(repo_path, '.gitmodules')):
        subprocess.run(
            ['git', 'submodule', 'update'], cwd=repo_path, check=True)


def clone_or_update(repo, dest_dir):
    '''
    Clone ``repo`` into ``dest_dir`` if absent, otherwise update it in place.

    Args:
        repo: (github.Repository) repository to back up
        dest_dir: (str) directory that holds the local clone

    Returns:
        None
    '''

    repo_path = os.path.join(dest_dir, repo.name)

    if os.path.isdir(repo_path):
        update_repo(repo_path)
    else:
        clone_repo(repo, repo_path)


def ensure_sub_dir(parent, name):
    '''
    Return the path to a subdirectory of ``parent``, creating it if needed.

    Args:
        parent: (str) path of the parent directory
        name: (str) name of the subdirectory

    Returns:
        (str) absolute path to the subdirectory
    '''

    sub_dir = os.path.join(parent, name)
    os.makedirs(sub_dir, exist_ok=True)

    return sub_dir


def classify_repo(repo, user, org_logins):
    '''
    Determine which backup subdirectory a repository belongs in.

    Repos owned by ``user`` are 'personal'. For repos owned by someone else,
    the user must be a contributor for the repo to be backed up: those owned by
    one of the user's organizations are filed under the org login, and the rest
    under 'contributed'.

    Args:
        repo: (github.Repository) repository to classify
        user: (str) login of the authenticated user
        org_logins: (list) organization logins the user belongs to

    Returns:
        (str or None) the category/subdirectory name, or None if the repo
        should be skipped (user is not the owner or a contributor)
    '''

    owner = repo.owner.login

    if owner == user:
        return 'personal'

    # Only back up other people's repos the user has actually contributed to.
    if user not in (c.login for c in repo.get_contributors()):
        return None

    return owner if owner in org_logins else 'contributed'


def print_summary(counts, org_logins, exceptions):
    '''
    Print a human-readable summary of the backup run.

    Args:
        counts: (dict) maps each category ('personal', 'contributed', and one
            entry per organization login) to the number of repos backed up
        org_logins: (list) organization logins, used to order the org lines
        exceptions: (list) names of repos that failed to clone or update

    Returns:
        None
    '''

    divider = '=' * 38

    print('\n\nFinished GitHub backup!\n')
    print(divider)
    print('\tSummary')
    print(divider)
    print(f"Updated {counts['personal']} personal repos")
    print(f"Updated {counts['contributed']} contributed repos")

    for org in org_logins:
        print(f'Updated {counts[org]} {org} repos')

    if exceptions:
        print(f'\n{divider}')
        print('The following repositories were not cloned/updated.')
        print('Please back them up manually.\n')
        for i, name in enumerate(exceptions, 1):
            print(f'{i}. {name}')

    print(f'\n{divider}\n')


def main(path):

    # !!! DO NOT EVER USE HARD-CODED VALUES HERE !!!
    # Instead, set and test environment variables, see README for info
    token = os.environ.get('GH_ACCSS_TKN')
    if not token:
        sys.exit('Error: environment variable GH_ACCSS_TKN is not set. '
                 'See the README for setup instructions.')

    g = Github(token)
    me = g.get_user()
    user = me.login
    org_logins = [org.login for org in me.get_orgs()]

    path = parse_path(path)
    os.makedirs(path, exist_ok=True)

    counts = {'personal': 0, 'contributed': 0}
    counts.update({org: 0 for org in org_logins})
    exceptions = []

    for repo in me.get_repos():
        try:
            category = classify_repo(repo, user, org_logins)
            if category is None:
                continue

            print(f'\n{category} repo: {repo.name}')
            sub_dir = ensure_sub_dir(path, category)
            clone_or_update(repo, sub_dir)
            counts[category] += 1
        except Exception as err:
            print(f'Error cloning/updating {repo.name}: {err}')
            exceptions.append(repo.name)

    print_summary(counts, org_logins, exceptions)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Back up all of a user\'s GitHub repositories to a '
                    'local directory')
    parser.add_argument(
        '-p', '--path',
        default='/mnt/d/Sync/GitHub',
        help='destination path for the backup')
    args = parser.parse_args()

    print(f'Backup will be created in path {args.path}')
    answer = input('Confirm the path [Y/n]: ')
    if answer.strip().lower() != 'y':
        sys.exit(1)

    main(args.path)
