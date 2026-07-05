from github import Auth, Github

import argparse
import os
import subprocess
import sys

from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Structured results
# --------------------------------------------------------------------------- #

@dataclass
class RepoTarget:
    '''
    A repository that is eligible for backup, resolved to a local location.

    Attributes:
        repo: (github.Repository) the GitHub repository
        category: (str) backup subdirectory ('personal', 'contributed', or an
            organization login)
        repo_path: (str) absolute path where the local clone lives / will live
        exists: (bool) whether ``repo_path`` is already a directory on disk
    '''

    repo: object
    category: str
    repo_path: str
    exists: bool


@dataclass
class RepoResult:
    '''
    The outcome of backing up a single repository.

    Attributes:
        name: (str) repository name
        category: (str) backup subdirectory it was filed under
        status: (str) one of 'cloned', 'updated', 'unchanged', 'skipped',
            'failed', or, in --dry-run mode, 'would-clone' / 'would-update'
        detail: (str) extra context, e.g. the error message when 'failed'
    '''

    name: str
    category: str
    status: str
    detail: str = ''


# --------------------------------------------------------------------------- #
# Path / classification helpers
# --------------------------------------------------------------------------- #

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


def parse_selection(response, count):
    '''
    Parse a user's numbered-menu response into a set of 0-based indices.

    Accepts a comma-separated mix of single numbers and ``a-b`` ranges, plus
    the keywords ``all`` and ``none``. An empty response defaults to ``all``.
    Numbers are 1-based in the input; out-of-range and unparseable tokens are
    ignored so a stray character never aborts a run.

    Args:
        response: (str) the raw line typed by the user
        count: (int) number of items in the menu

    Returns:
        (set) selected indices in the range ``0 .. count - 1``
    '''

    response = response.strip().lower()

    if response in ('', 'all', 'a'):
        return set(range(count))
    if response in ('none', 'n'):
        return set()

    selected = set()
    for token in response.split(','):
        token = token.strip()
        if not token:
            continue

        if '-' in token:
            lo, _, hi = token.partition('-')
            try:
                lo, hi = int(lo), int(hi)
            except ValueError:
                continue
            for i in range(lo, hi + 1):
                if 1 <= i <= count:
                    selected.add(i - 1)
        else:
            try:
                i = int(token)
            except ValueError:
                continue
            if 1 <= i <= count:
                selected.add(i - 1)

    return selected


# --------------------------------------------------------------------------- #
# Git operations
# --------------------------------------------------------------------------- #

def git_head(repo_path):
    '''
    Return the current ``HEAD`` commit sha of a local repository.

    Args:
        repo_path: (str) path to the local clone

    Returns:
        (str or None) the HEAD sha, or None if it cannot be determined
    '''

    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=repo_path, capture_output=True, text=True)

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def clone_repo(repo, repo_path, out=sys.stderr):
    '''
    Clone a repository into ``repo_path`` and initialize its submodules.

    Args:
        repo: (github.Repository) repository to clone
        repo_path: (str) destination directory for the clone
        out: (file) where git's stdout is sent; defaults to stderr so it never
            pollutes the machine-readable stdout. Pass ``subprocess.DEVNULL``
            to silence git entirely.

    Returns:
        None

    Raises:
        subprocess.CalledProcessError: if ``git clone`` or the submodule
            update exits with a non-zero status.
    '''

    subprocess.run(
        ['git', 'clone', repo.ssh_url, repo_path],
        check=True, stdout=out)
    if os.path.exists(os.path.join(repo_path, '.gitmodules')):
        subprocess.run(
            ['git', 'submodule', 'update', '--init'],
            cwd=repo_path, check=True, stdout=out)


def update_repo(repo_path, out=sys.stderr):
    '''
    Pull the latest changes for an existing clone and refresh its submodules.

    Args:
        repo_path: (str) path to the existing local clone
        out: (file) where git's stdout is sent; defaults to stderr so it never
            pollutes the machine-readable stdout. Pass ``subprocess.DEVNULL``
            to silence git entirely (e.g. hide "Already up to date.").

    Returns:
        (bool) True if the pull advanced ``HEAD`` (new commits were fetched),
        False if the repository was already up to date.

    Raises:
        subprocess.CalledProcessError: if ``git pull`` or the submodule
            update exits with a non-zero status.
    '''

    before = git_head(repo_path)

    subprocess.run(
        ['git', 'pull', '--all'], cwd=repo_path, check=True, stdout=out)
    if os.path.exists(os.path.join(repo_path, '.gitmodules')):
        subprocess.run(
            ['git', 'submodule', 'update'],
            cwd=repo_path, check=True, stdout=out)

    after = git_head(repo_path)

    return before != after


def check_repo(repo_path, out=sys.stderr):
    '''
    Report whether an existing clone is behind its upstream — without merging,
    checking out, or otherwise touching the working tree or local branches.
    Used by ``--dry-run`` to preview what an update would do.

    Runs ``git fetch --all`` (which only updates remote-tracking refs) and then
    counts how many commits the current branch's upstream has that ``HEAD``
    does not.

    Args:
        repo_path: (str) path to the existing local clone
        out: (file) where git's output is sent (see ``update_repo``)

    Returns:
        (bool) True if the upstream is ahead of ``HEAD`` (a pull would bring in
        new commits); False if already current or there is no upstream branch
        to compare against.

    Raises:
        subprocess.CalledProcessError: if ``git fetch`` exits non-zero.
    '''

    subprocess.run(
        ['git', 'fetch', '--all'],
        cwd=repo_path, check=True, stdout=out, stderr=out)

    result = subprocess.run(
        ['git', 'rev-list', '--count', 'HEAD..@{u}'],
        cwd=repo_path, capture_output=True, text=True)

    if result.returncode != 0:  # no upstream / detached HEAD
        return False

    return int(result.stdout.strip() or 0) > 0


# --------------------------------------------------------------------------- #
# Backup engine
# --------------------------------------------------------------------------- #

class GitHubBackup:
    '''
    Backup engine: discovers a user's repositories and clones/updates them.

    The engine performs no user interaction and does not print progress on its
    own beyond the underlying git commands; callers (the CLI here, a GUI later)
    drive it and interpret the returned ``RepoResult`` objects.
    '''

    def __init__(self, token, dest_root):
        '''
        Args:
            token: (str) GitHub personal access token
            dest_root: (str) root directory for the backup tree
        '''

        self.github = Github(auth=Auth.Token(token))
        self.me = self.github.get_user()
        self.user = self.me.login
        self.org_logins = [org.login for org in self.me.get_orgs()]
        self.dest_root = parse_path(dest_root)

    def discover(self):
        '''
        Yield a ``RepoTarget`` for every backup-eligible repository.

        Repos the user neither owns nor contributes to are skipped (see
        ``classify_repo``).

        Yields:
            (RepoTarget) one per eligible repository
        '''

        for repo in self.me.get_repos():
            category = classify_repo(repo, self.user, self.org_logins)
            if category is None:
                continue

            repo_path = os.path.join(self.dest_root, category, repo.name)
            yield RepoTarget(
                repo=repo,
                category=category,
                repo_path=repo_path,
                exists=os.path.isdir(repo_path))

    def process(self, target, out=sys.stderr, dry_run=False):
        '''
        Clone or update a single target and return its result.

        A missing repo is cloned ('cloned'); an existing repo is pulled and
        reported as 'updated' (new commits) or 'unchanged'. Any failure is
        captured as 'failed' with the error text rather than raised.

        When ``dry_run`` is set nothing on disk is changed: a missing repo is
        reported as 'would-clone', and an existing repo is fetched (refs only)
        and reported as 'would-update' or 'unchanged'.

        Args:
            target: (RepoTarget) the repository to back up
            out: (file) where git's stdout is routed (see ``update_repo`` /
                ``clone_repo``); defaults to stderr.
            dry_run: (bool) preview only — do not clone or pull anything.

        Returns:
            (RepoResult) the outcome
        '''

        name = target.repo.name

        try:
            if dry_run:
                if target.exists:
                    would = check_repo(target.repo_path, out=out)
                    status = 'would-update' if would else 'unchanged'
                else:
                    status = 'would-clone'
            elif target.exists:
                changed = update_repo(target.repo_path, out=out)
                status = 'updated' if changed else 'unchanged'
            else:
                ensure_sub_dir(self.dest_root, target.category)
                clone_repo(target.repo, target.repo_path, out=out)
                status = 'cloned'

            return RepoResult(name, target.category, status)
        except Exception as err:
            return RepoResult(name, target.category, 'failed', str(err))


# --------------------------------------------------------------------------- #
# CLI presentation
# --------------------------------------------------------------------------- #

def prompt_selection(targets, stream=sys.stderr):
    '''
    Ask the user which of the existing repos to update via a numbered menu.

    Falls back to selecting everything when stdin is not a TTY (cron, pipes),
    so the flow never blocks in non-interactive contexts.

    Args:
        targets: (list) existing ``RepoTarget`` objects to choose from
        stream: (file) where to write the menu (stderr by default so stdout
            stays clean for machine-readable output)

    Returns:
        (list) the subset of ``targets`` the user chose to update
    '''

    if not targets or not sys.stdin.isatty():
        return targets

    print('\nRepositories already backed up (choose which to update):',
          file=stream)
    for i, target in enumerate(targets, 1):
        print(f'  {i}. {target.category}/{target.repo.name}', file=stream)
    print("Enter numbers/ranges (e.g. 1,3,5-8), 'all', or 'none' "
          "[default: all]: ", end='', file=stream, flush=True)

    chosen = parse_selection(input(), len(targets))
    return [target for i, target in enumerate(targets) if i in chosen]


def print_summary(results, stream=sys.stderr):
    '''
    Print a human-readable summary of a backup run.

    Args:
        results: (list) ``RepoResult`` objects from the run
        stream: (file) where to write the summary (stderr by default)

    Returns:
        None
    '''

    divider = '=' * 38
    labels = {
        'cloned': 'Cloned', 'would-clone': 'Would clone',
        'updated': 'Updated', 'would-update': 'Would update',
        'unchanged': 'Unchanged', 'failed': 'Failed'}
    order = ['cloned', 'would-clone', 'updated', 'would-update',
             'unchanged', 'failed']
    buckets = {status: [] for status in order}
    for result in results:
        buckets.setdefault(result.status, []).append(result)

    dry_run = bool(buckets['would-clone'] or buckets['would-update'])
    print('\n\nFinished GitHub backup (dry run)!\n' if dry_run
          else '\n\nFinished GitHub backup!\n', file=stream)
    print(divider, file=stream)
    print('\tSummary', file=stream)
    print(divider, file=stream)
    for status in order:
        if buckets[status]:  # hide the zero rows for the other mode
            print(f'{labels[status]}: {len(buckets[status])}', file=stream)

    for status, header in (('updated', 'Updated repositories:'),
                           ('would-update', 'Repositories that would update:'),
                           ('would-clone', 'Repositories that would be cloned:')):
        if buckets[status]:
            print(f'\n{divider}', file=stream)
            print(header, file=stream)
            for result in buckets[status]:
                print(f'  {result.category}/{result.name}', file=stream)

    if buckets['failed']:
        print(f'\n{divider}', file=stream)
        print('The following repositories were not cloned/updated.', file=stream)
        print('Please back them up manually.\n', file=stream)
        for i, result in enumerate(buckets['failed'], 1):
            print(f'{i}. {result.name}: {result.detail}', file=stream)

    print(f'\n{divider}\n', file=stream)


def status(msg, transient=False, stream=sys.stderr):
    '''
    Print a live status line to ``stream`` (stderr by default).

    When ``transient`` is true the message is a progress indicator: on a TTY
    it is written with a carriage return and cleared to end-of-line so the
    next status overwrites it in place (``msg=''`` just clears the line), and
    on a non-TTY (log/pipe) it is skipped entirely rather than spamming full
    lines. When ``transient`` is false a normal, newline-terminated line is
    printed (empty messages are ignored).

    Args:
        msg: (str) the message to show
        transient: (bool) overwrite-in-place instead of scrolling
        stream: (file) destination (stderr by default)

    Returns:
        None
    '''

    if transient:
        if stream.isatty():
            print(f'\r\033[K{msg}', end='', file=stream, flush=True)
    elif msg:
        print(msg, file=stream, flush=True)


def run_backup(backup, update_all, list_updated, dry_run=False):
    '''
    Drive a full backup run and report according to the selected CLI mode.

    Missing repos are always cloned. Existing repos are updated either after an
    interactive selection prompt or, when ``update_all`` is set (or stdin is not
    a TTY), all of them.

    Args:
        backup: (GitHubBackup) the configured engine
        update_all: (bool) skip the selection prompt and update every existing
            repo
        list_updated: (bool) machine-readable mode: print only the names of
            repos that received new commits (one per line) to stdout
        dry_run: (bool) preview only — fetch and report what would be cloned or
            updated without changing anything on disk

    Returns:
        (list) the ``RepoResult`` objects from the run
    '''

    # Discovery is the slow, silent phase (a contributor lookup per repo), so
    # show it's alive and count repos as they come in.
    status('Discovering repositories ...')
    targets = []
    for target in backup.discover():
        targets.append(target)
        status(f'Discovering repositories ... {len(targets)} found',
               transient=True)
    status('', transient=True)  # clear the transient discovery line
    status(f'Found {len(targets)} repositories to consider.')

    missing = [t for t in targets if not t.exists]
    existing = [t for t in targets if t.exists]

    # --dry-run and --list-updated both consider every existing repo, no prompt.
    if update_all or list_updated or dry_run:
        to_update = existing
    else:
        to_update = prompt_selection(existing)

    # In the "report" modes (--list-updated / --dry-run) silence git entirely
    # (no "Already up to date." / fetch chatter) and show progress on a single
    # self-overwriting line, so only the meaningful results are left on screen.
    report_mode = list_updated or dry_run
    git_out = subprocess.DEVNULL if report_mode else sys.stderr

    work = missing + to_update
    total = len(work)
    results = []
    for i, target in enumerate(work, 1):
        if dry_run:
            action = 'Would clone' if not target.exists else 'Checking'
        else:
            action = 'Cloning' if not target.exists else 'Updating'
        status(f'[{i}/{total}] {action} {target.category}/{target.repo.name} ...',
               transient=report_mode)
        result = backup.process(target, out=git_out, dry_run=dry_run)
        results.append(result)
        if list_updated and result.status in ('updated', 'would-update'):
            status('', transient=True)  # clear progress before the name
            print(result.name, flush=True)
    if report_mode:
        status('', transient=True)  # clear the final progress line
    if list_updated:
        changed = sum(r.status in ('updated', 'would-update') for r in results)
        verb = 'would be updated' if dry_run else 'updated'
        status(f'Done. {changed} of {total} repositories {verb}.')

    if not list_updated:
        print_summary(results)

    return results


def main(path, update_all=False, list_updated=False, dry_run=False):
    # !!! DO NOT EVER USE HARD-CODED VALUES HERE !!!
    # Instead, set and test environment variables, see README for info
    token = os.environ.get('GH_ACCSS_TKN')
    if not token:
        sys.exit('Error: environment variable GH_ACCSS_TKN is not set. '
                 'See the README for setup instructions.')

    backup = GitHubBackup(token, path)
    run_backup(backup, update_all=update_all, list_updated=list_updated,
               dry_run=dry_run)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Back up all of a user\'s GitHub repositories to a '
                    'local directory')
    parser.add_argument(
        '-p', '--path',
        default='/mnt/e/GitHub',
        help='destination path for the backup')
    parser.add_argument(
        '-a', '--all', '-y', '--yes',
        dest='update_all', default=False, action='store_true',
        help='update every existing repo without the interactive prompt')
    parser.add_argument(
        '--list-updated',
        default=False, action='store_true',
        help='print only the names of repos that received new commits, one '
             'per line (implies --all; suppresses the summary on stdout)')
    parser.add_argument(
        '-n', '--dry-run',
        default=False, action='store_true',
        help='preview only: fetch and report which repos would be cloned or '
             'updated, without changing anything on disk')
    args = parser.parse_args()

    # In interactive, human-facing mode, confirm the destination first. A dry
    # run touches nothing, so there is nothing to confirm.
    if not args.list_updated and not args.dry_run and sys.stdin.isatty():
        print(f'Backup will be created in path {args.path}')
        answer = input('Confirm the path [Y/n]: ')
        if answer.strip().lower() != 'y':
            sys.exit(1)

    main(args.path, update_all=args.update_all, list_updated=args.list_updated,
         dry_run=args.dry_run)
