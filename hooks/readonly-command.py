#!/usr/bin/env python3
# sliceworks 0.8.9. Standard library only; missing/invalid classification denies.
"""Conservative STOP-time inspection classifier. Never execute the supplied command.
Unknown programs, shell composition, interpreters and write-capable options deny.
"""
import json
import re
import shlex
import sys


def options(args, plain=(), valued=()):
    """Only known flags; operands after -- are literal."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--':
            return True
        if arg.startswith('-') and arg != '-':
            key, sep, value = arg.partition('=')
            if arg in plain:
                pass
            elif key in valued:
                if not sep:
                    i += 1
                    if i >= len(args) or args[i].startswith('-'):
                        return False
            elif not re.fullmatch(r'-[0-9]+', arg):
                return False
        i += 1
    return True


def allowed(command):
    if not isinstance(command, str) or not command.strip():
        return False
    # Reject even quoted metacharacters: deliberate conservative false negatives.
    if any(char in command for char in "\n\r\x00$`;|&<>(){}\\*?[]~!"):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    exe, *args = argv
    if '/' in exe and exe.rsplit('/', 1)[0] not in ('/bin', '/usr/bin', '/usr/local/bin', '/opt/homebrew/bin'):
        return False
    exe = exe.rsplit('/', 1)[-1]
    if exe == 'pwd':
        return all(a in ('-L', '-P') for a in args)
    if exe in ('cat', 'ls', 'wc', 'readlink', 'realpath', 'basename', 'dirname'):
        # These programs have no command-execution or output-file options.
        return True
    if exe in ('head', 'tail'):
        return options(args, ('-q', '-v', '--quiet', '--verbose'), ('-n', '-c', '--lines', '--bytes'))
    if exe == 'sed':
        # Print ranges only, never sed w/e, -i or script files.
        return len(args) >= 3 and args[0] == '-n' and bool(re.fullmatch(r'[0-9]+(?:,(?:[0-9]+|[$]))?p', args[1])) and all(not a.startswith('-') for a in args[2:])
    if exe == 'rg':
        if '--no-config' not in args:
            return False
        return options(args,
            ('--no-config', '--files', '--hidden', '--no-ignore', '--no-ignore-vcs', '-n', '--line-number', '-l', '--files-with-matches', '--files-without-match', '-i', '--ignore-case', '-S', '--smart-case', '-F', '--fixed-strings', '-w', '--word-regexp', '-x', '--line-regexp', '-v', '--invert-match', '-c', '--count', '--count-matches', '-o', '--only-matching', '-H', '--with-filename', '--heading', '--no-heading', '--no-messages', '--stats', '-u', '-uu', '-uuu'),
            ('-g', '--glob', '-e', '--regexp', '-t', '--type', '-T', '--type-not', '-m', '--max-count', '-A', '--after-context', '-B', '--before-context', '-C', '--context', '--max-depth', '--color'))
    if exe == 'git':
        configs = set()
        globals_ = set()
        while args and args[0].startswith('-'):
            arg = args.pop(0)
            if arg == '-C' and args:
                args.pop(0)
            elif arg == '-c' and args and args[0] in ('core.fsmonitor=', 'core.hooksPath=/dev/null', 'diff.external=', 'log.showSignature=false'):
                configs.add(args.pop(0))
            elif arg in ('--no-pager', '--no-optional-locks'):
                globals_.add(arg)
            else:
                return False
        if not args:
            return False
        sub, *rest = args
        if sub == 'remote':
            return rest in ([], ['-v'], ['--verbose'])
        if sub == 'rev-parse':
            return options(rest, ('--show-toplevel', '--git-common-dir', '--git-dir', '--absolute-git-dir', '--verify', '--short', '--abbrev-ref', '--is-inside-work-tree'), ('--path-format',))
        if sub == 'merge-base':
            return options(rest, ('--all', '-a', '--is-ancestor', '--octopus', '--independent', '--fork-point'))
        if sub in ('ls-files', 'ls-tree'):
            if sub == 'ls-files' and not ('--no-optional-locks' in globals_ and 'core.fsmonitor=' in configs):
                return False
            return options(rest, ('-r', '-t', '-z', '-s', '--stage', '--cached', '--others', '--exclude-standard', '--name-only', '--name-status', '--full-tree', '--full-name', '--long', '-l', '--error-unmatch'))
        if '--no-pager' not in globals_:
            return False
        if sub == 'status':
            return '--no-optional-locks' in globals_ and 'core.fsmonitor=' in configs and options(rest, ('--short', '-s', '--branch', '-b', '--porcelain', '--porcelain=v1', '--porcelain=v2', '--untracked-files=no', '--untracked-files=all'))
        if sub in ('diff', 'show', 'log', 'blame'):
            if sub == 'log' and 'log.showSignature=false' not in configs:
                return False
            if sub == 'diff' and not ('--no-optional-locks' in globals_ and 'core.fsmonitor=' in configs):
                return False
            if (sub in ('diff', 'show') or sub == 'log' and any(x in rest for x in ('-p', '--patch'))) and not all(x in rest for x in ('--no-ext-diff', '--no-textconv')):
                return False
            return options(rest,
                ('--no-ext-diff', '--no-textconv', '--stat', '--numstat', '--shortstat', '--name-only', '--name-status', '--summary', '--oneline', '--decorate', '--no-decorate', '--all', '--first-parent', '--no-merges', '--reverse', '--raw', '--patch', '-p', '--no-patch', '-s', '--check', '--cached', '--staged', '--no-color', '--date-order', '--topo-order'),
                ('--format', '--pretty', '--date', '--max-count', '-n', '--since', '--until', '--author', '--grep', '--diff-filter', '--unified', '-U', '-L'))
        return False
    if exe == 'gh':
        if len(args) < 2:
            return False
        family, action, *rest = args
        if (family, action) not in (('pr', 'view'), ('pr', 'diff'), ('pr', 'checks'), ('repo', 'view'), ('auth', 'status')):
            return False
        return options(rest, ('--patch', '--name-only', '--no-color', '--required', '--active'), ('--repo', '-R', '--json', '--jq', '-q', '--hostname', '-h'))
    return False


def main():
    try:
        data = json.load(sys.stdin)
        tool = data.get('tool_name')
        command = data.get('tool_input', {}).get('command')
        return 0 if tool == 'Bash' and allowed(command) else 1
    except (ValueError, TypeError, AttributeError):
        return 1


if __name__ == '__main__':
    sys.exit(main())
