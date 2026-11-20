#!/usr/bin/env python3
"""Table test for guard.py. Run: python3 .claude/hooks/test_guard.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
SCOPE = {"frontend_dirs": ["web"], "backend_dirs": ["api"], "test_dirs": ["tests"],
         "migration_dirs": ["api/db/migrations"]}


def run(project, role, tool, tool_input):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    payload = {"agent_type": role, "tool_name": tool, "tool_input": tool_input, "cwd": project}
    p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), capture_output=True, text=True, env=env)
    if p.returncode == 2:
        return "deny"
    if p.stdout.strip():
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]
    return "allow"


def B(cmd):
    return ("Bash", {"command": cmd})


def W(path):
    return ("Write", {"file_path": path, "content": "x"})


CASES = [
    # Bash, all roles
    ("backend-dev", *B("git commit -m 'T-01: add login'"), "allow"),
    ("backend-dev", *B("git commit -m 'x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'"), "deny"),
    ("backend-dev", *B("gh pr create --title t --body '\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)'"), "deny"),
    ("backend-dev", *B("git add -A"), "deny"),
    ("backend-dev", *B("git add ."), "deny"),
    ("backend-dev", *B("git add api/users.py"), "allow"),
    ("backend-dev", *B("git add .blackboard/tasks/T-01.md"), "deny"),
    ("frontend-dev", *B("git reset --hard HEAD~1"), "deny"),
    ("frontend-dev", *B("git checkout -- web/app.tsx"), "deny"),
    ("frontend-dev", *B("git checkout -b feat/T-01-login"), "allow"),
    ("frontend-dev", *B("git commit -m 'note: never run git reset --hard'"), "allow"),
    ("orchestrator", *B("git push origin feat/x"), "ask"),
    ("orchestrator", *B("git push --force origin feat/x"), "ask"),
    ("orchestrator", *B("git pull origin main"), "allow"),
    ("orchestrator", *B("gh pr merge 3"), "deny"),
    ("orchestrator", *B("gh pr create --title t --body b"), "ask"),
    ("frontend-dev", *B("rm -rf web/old"), "ask"),
    ("frontend-dev", *B("npm install lodash"), "ask"),
    ("frontend-dev", *B("npm install"), "allow"),
    ("backend-dev", *B("pip install requests"), "ask"),
    ("backend-dev", *B("alembic upgrade head"), "ask"),
    ("backend-dev", *B("python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py 'x' --persist"), "ask"),
    ("frontend-dev", *B("python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py 'x' --domain ux --force"), "deny"),
    ("backend-dev", *B("pytest -q"), "allow"),
    # PR review commands
    ("reviewer", *B("gh pr diff 3"), "allow"),
    ("reviewer", *B("gh api repos/o/r/pulls/3/reviews --input review.json"), "allow"),
    ("reviewer", *B("gh pr review 3 --approve"), "deny"),
    ("reviewer", *B("gh api repos/o/r/pulls/3/reviews -f event=APPROVE"), "deny"),
    ("reviewer", *B("gh pr review 3 --comment --body-file b.md"), "allow"),
    ("frontend-dev", *B("gh pr comment 3 --body hi"), "deny"),
    # reviewer is read-only
    ("reviewer", *B("git show abc123"), "allow"),
    ("reviewer", *B("git diff abc..def"), "allow"),
    ("reviewer", *B("git commit -m x"), "deny"),
    ("reviewer", *B("sed -i 's/a/b/' api/x.py"), "deny"),
    ("reviewer", *B("echo hi > api/x.py"), "deny"),
    ("reviewer", *B("cat >> .blackboard/tasks/T-01.md <<'EOF'\nfinding\nEOF"), "allow"),
    ("reviewer", *B("gh pr diff 3 2>/dev/null | head"), "allow"),
    # paths
    ("frontend-dev", *W("web/src/App.tsx"), "allow"),
    ("frontend-dev", *W("api/users.py"), "deny"),
    ("frontend-dev", *W("web/src/App.test.tsx"), "deny"),
    ("frontend-dev", *W("web/package.json"), "ask"),
    ("frontend-dev", *W(".blackboard/tasks/T-01.md"), "allow"),
    ("frontend-dev", *W(".blackboard/BOARD.md"), "deny"),
    ("frontend-dev", *W("AGENTS.md"), "deny"),
    ("frontend-dev", *W(".claude/settings.json"), "deny"),
    ("frontend-dev", *W("web/../api/users.py"), "deny"),
    ("frontend-dev", *W("/etc/hosts"), "deny"),
    ("backend-dev", *W("api/users.py"), "allow"),
    ("backend-dev", *W("api/db/migrations/001.sql"), "ask"),
    ("backend-dev", *W("api/test_users.py"), "deny"),
    ("backend-dev", *W(".github/workflows/ci.yml"), "deny"),
    ("tester", *W("tests/test_users.py"), "allow"),
    ("tester", *W("web/src/App.test.tsx"), "allow"),
    ("tester", *W("api/users.py"), "deny"),
    ("reviewer", *W(".blackboard/tasks/T-01.md"), "allow"),
    ("reviewer", *W("api/users.py"), "deny"),
    ("orchestrator", *W(".blackboard/BOARD.md"), "allow"),
    ("orchestrator", *W(".blackboard/BOARD.template.md"), "ask"),
    ("orchestrator", *W("api/users.py"), "deny"),
    # unknown agent / plain session: never interfered with
    ("", *B("git push --force"), "allow"),
    ("general-purpose", *W("api/users.py"), "allow"),
    ("plugin:frontend-dev", *W("api/users.py"), "deny"),
]


def main():
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.realpath(tmp)
        os.makedirs(os.path.join(project, ".claude"))
        with open(os.path.join(project, ".claude", "scope.json"), "w") as f:
            json.dump(SCOPE, f)
        for role, tool, tin, want in CASES:
            got = run(project, role, tool, tin)
            if got != want:
                bad += 1
                print("FAIL %-14s %-5s want=%-5s got=%-5s %s" % (role, tool, want, got, json.dumps(tin)[:90]))
        # unconfigured scope.json must fail closed for workers
        with open(os.path.join(project, ".claude", "scope.json"), "w") as f:
            json.dump({"frontend_dirs": ["[FRONTEND_DIR]"]}, f)
        got = run(project, "frontend-dev", *W("web/src/App.tsx"))
        if got != "deny":
            bad += 1
            print("FAIL placeholder scope should deny, got", got)
    total = len(CASES) + 1
    print("%d/%d passed" % (total - bad, total))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
