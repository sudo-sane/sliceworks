# STOP-time inspection

[Method chapter 10](../method/10-autonomous-operation.md#safety-rails) owns the stop rule. These hooks implement it without changing the STOP marker.

When an adopted project has STOP and package hooks are enabled, `kill-switch.sh` passes normalized shell input to the bundled `readonly-command.py`. The classifier parses text only; it never evaluates or executes the requested command. Only known inspection programs and options pass. All other matched tool calls deny, including edits, agent launches, worker messages and continuations. The budget guard also checks STOP before its explorer exemption.

Supported reads include `pwd`, `cat`, `ls`, `wc`, bounded `head`/`tail`, numeric print ranges with `sed -n`, `rg --no-config`, selected Git reads and selected `gh pr`, `gh repo view` and `gh auth status` calls. The classifier source is the complete option allowlist. For example:

```sh
cat README.md
sed -n '1,40p' README.md
rg --no-config -n -F STOP hooks
git remote -v
git --no-pager -c log.showSignature=false log --max-count=5 --oneline
git --no-optional-locks -c core.fsmonitor= --no-pager status --short
git --no-optional-locks -c core.fsmonitor= --no-pager diff --no-ext-diff --no-textconv --stat
gh pr view 13 --repo owner/project --json title,body
```

The policy deliberately rejects shell composition, redirects, substitution, expansion and glob metacharacters, even when quoted. Use separate calls and literal paths. Interpreters, arbitrary scripts, Git mutations, output-file options, ripgrep preprocessors and browser-launch options deny. Git inspection that can consult the index requires optional writes and fsmonitor to be disabled; log inspection disables configured signature helpers; diff/patch inspection disables external diff and text conversion. Ripgrep ignores ambient config. Standard executable names and the supported system binary directories are assumed to resolve to trusted programs; this classifier does not replace the runtime sandbox or secure a hostile PATH or shell startup configuration.

Missing Python, a missing classifier, malformed input or a classifier error denies while STOP is present. Without project configuration, without STOP, or with the existing `SW_PLUGIN_HOOKS=off` configuration, the existing inert behavior remains. Permission to inspect does not launch verification suites, models, providers or the application.

The plugin ships the classifier beside the shell hook. Copy installation generates `.codex/hooks.json` pointing to that same hook directory, so it needs no cache patch or copied classifier. Regenerate machine-local hook commands when changing installation roots; see the [Codex adapter](../scripts/runtimes/codex/README.md#updating-a-project-local-copy-from-080). Do not leave an installation pinned to an obsolete versioned cache path.

Regression checks: `python3 -m unittest discover -s tests -p test_readonly_command.py` and `sh tests/test_hooks.sh`. They use disposable projects and never dispatch a model.
