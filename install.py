#!/usr/bin/env python3
"""Install or update the orchestrator-worker team in another project.

    python3 install.py /path/to/project [--update] [--dry-run] [--base BRANCH]

Copies the team files that sit next to this script into the project. It never overwrites a
file you changed and never touches .claude/scope.json once that exists. A hash of every file
it installed is kept in .claude/team-install.json, so --update can tell your edits apart.
Exit code 1 means at least one CONFLICT needs a manual merge.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANAGED = [
    "AGENTS.md",
    ".claude/agents/orchestrator.md", ".claude/agents/frontend-dev.md", ".claude/agents/backend-dev.md",
    ".claude/agents/reviewer.md", ".claude/agents/tester.md",
    ".claude/hooks/guard.py", ".claude/hooks/test_guard.py",
    ".blackboard/BOARD.template.md", ".blackboard/TASK.template.md",
]
STATE = ".claude/team-install.json"
GITIGNORE = [".blackboard/BOARD.md", ".blackboard/tasks/", ".blackboard/archive/"]
MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Bash"
HOOK_CMD = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"'
SKILLS = ["senior-fullstack", "ui-ux-pro-max", "sql-optimizer", "refactor"]
CANDIDATES = {
    "frontend_dirs": ["web", "frontend", "client", "apps/web", "src/web"],
    "backend_dirs": ["api", "backend", "server", "apps/api", "src/api"],
    "test_dirs": ["tests", "test", "__tests__", "spec"],
    "migration_dirs": ["migrations", "db/migrations", "prisma/migrations", "alembic/versions", "database/migrations"],
}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run(*cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--update", action="store_true", help="overwrite managed files you have not changed")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    ap.add_argument("--base", help="base branch (default: detected from origin, else main)")
    a = ap.parse_args()
    proj = os.path.abspath(os.path.expanduser(a.project))
    if not os.path.isdir(proj):
        sys.exit("not a directory: " + proj)
    if os.path.realpath(proj) == os.path.realpath(HERE):
        sys.exit("the target is the team repo itself")
    dry = a.dry_run

    def say(tag, text):
        print("%-9s %s" % (tag, text))

    def write(rel, data):
        if dry:
            return
        dst = os.path.join(proj, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w") as f:
            f.write(data)

    def copy(rel):
        with open(os.path.join(HERE, rel)) as f:
            write(rel, f.read())
        if rel.endswith(".py") and not dry:
            os.chmod(os.path.join(proj, rel), 0o755)

    state_path = os.path.join(proj, STATE)
    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception:
        state = {"files": {}}
    conflicts = 0

    for rel in MANAGED:
        src, dst = os.path.join(HERE, rel), os.path.join(proj, rel)
        want = sha(src)
        if not os.path.exists(dst):
            copy(rel)
            state["files"][rel] = want
            say("added", rel)
            continue
        cur = sha(dst)
        if cur == want:
            state["files"][rel] = want
            say("ok", rel)
        elif state["files"].get(rel) == cur:  # unchanged since we installed it
            if a.update:
                copy(rel)
                state["files"][rel] = want
                say("updated", rel)
            else:
                say("outdated", rel + "  (run with --update)")
        else:
            conflicts += 1
            extra = "  The team files refer to AGENTS.md sections: append ours to yours." if rel == "AGENTS.md" else ""
            say("CONFLICT", "%s  exists and differs. Merge by hand: diff %s %s.%s" % (rel, src, dst, extra))

    # .gitignore: add the three blackboard lines
    gi = os.path.join(proj, ".gitignore")
    old = open(gi).read() if os.path.exists(gi) else ""
    missing = [l for l in GITIGNORE if l not in old.splitlines()]
    if missing:
        write(".gitignore", old + ("" if old.endswith("\n") or not old else "\n") + "\n".join(missing) + "\n")
        say("merged", ".gitignore (+%d lines)" % len(missing))
    else:
        say("ok", ".gitignore")

    # CLAUDE.md: import AGENTS.md
    cm = os.path.join(proj, "CLAUDE.md")
    old = open(cm).read() if os.path.exists(cm) else ""
    if "@AGENTS.md" not in [l.strip() for l in old.splitlines()]:
        write("CLAUDE.md", old + ("" if old.endswith("\n") or not old else "\n") + "@AGENTS.md\n")
        say("merged", "CLAUDE.md (+@AGENTS.md)")
    else:
        say("ok", "CLAUDE.md")

    # .claude/settings.json: register the guard hook next to whatever hooks exist
    sp = os.path.join(proj, ".claude", "settings.json")
    try:
        settings = json.load(open(sp)) if os.path.exists(sp) else {}
    except ValueError:
        settings = None
    if settings is None:
        conflicts += 1
        say("CONFLICT", ".claude/settings.json is not valid JSON; add the guard hook by hand (see this repo's .claude/settings.json)")
    else:
        pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
        if any(h.get("command") == HOOK_CMD for e in pre for h in e.get("hooks", [])):
            say("ok", ".claude/settings.json")
        else:
            pre.append({"matcher": MATCHER, "hooks": [{"type": "command", "command": HOOK_CMD}]})
            write(".claude/settings.json", json.dumps(settings, indent=2) + "\n")
            say("merged", ".claude/settings.json (+guard hook)")

    # .claude/scope.json: create once, never overwrite
    scp = os.path.join(proj, ".claude", "scope.json")
    if os.path.exists(scp):
        say("kept", ".claude/scope.json")
    else:
        with open(os.path.join(HERE, ".claude", "scope.json")) as f:
            scope = json.load(f)
        scope["base_branch"] = a.base or detect_base(proj)
        write(".claude/scope.json", json.dumps(scope, indent=2) + "\n")
        say("created", ".claude/scope.json (base_branch=%s)" % scope["base_branch"])

    if not dry:
        write(STATE, json.dumps(state, indent=2, sort_keys=True) + "\n")

    print("\nNext: fill .claude/scope.json (dirs + commands).")
    for key, names in CANDIDATES.items():
        found = [n for n in names if os.path.isdir(os.path.join(proj, n))]
        if found:
            print("  %-15s found: %s" % (key, ", ".join(found)))
    print("\nChecks:")
    preflight(proj)
    if dry:
        print("\n(dry run: nothing was written)")
    sys.exit(1 if conflicts else 0)


def detect_base(proj):
    r = run("git", "-C", proj, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if r and r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("/", 1)[-1]
    return "main"


def preflight(proj):
    def line(ok, text):
        print("  %s %s" % ("ok  " if ok else "WARN", text))

    line(True, "python3 %d.%d" % sys.version_info[:2])
    r = run("gh", "auth", "status")
    if r is None:
        line(False, "gh (GitHub CLI) not installed; the Reviewer cannot read or comment on PRs")
    else:
        accts = re.findall(r"account (\S+) \([^)]*\)\s*\n\s*- Active account: (true|false)", r.stdout + r.stderr)
        active = [n for n, on in accts if on == "true"]
        if active:
            others = [n for n, on in accts if on == "false"]
            line(True, "gh active account: %s%s. PR comments post as this account%s" % (
                active[0], "" if not others else " (also logged in: %s)" % ", ".join(others),
                "" if not others else "; switch with gh auth switch -u <account>"))
        else:
            line(False, "gh is not logged in (gh auth login)")
    for s in SKILLS:
        have = os.path.isdir(os.path.expanduser("~/.claude/skills/" + s))
        line(have, "skill %s %s" % (s, "installed" if have else "missing in ~/.claude/skills (will be skipped, noted in Open Questions)"))
    if os.path.isdir(os.path.join(proj, ".git")):
        r = run("git", "-C", proj, "check-ignore", "-v", "CLAUDE.md")
        if r and r.returncode == 0:
            line(False, "CLAUDE.md is git-ignored (%s). Commit it with git add -f CLAUDE.md" % r.stdout.split("\t")[0].strip())
        else:
            line(True, "CLAUDE.md is not git-ignored")
    else:
        line(False, "target is not a git repository")


if __name__ == "__main__":
    main()
