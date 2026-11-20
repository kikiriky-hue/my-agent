#!/usr/bin/env python3
"""PreToolUse guard that enforces AGENTS.md (section 3f) for the five roles.

Reads the hook JSON on stdin and acts only when `agent_type` is one of ROLES, so plain
Claude Code sessions are not affected.
  exit 0, no output : no decision (normal permission flow)
  exit 0, JSON      : ask the human
  exit 2, stderr    : deny; the message goes back to the agent
Bash checks are best-effort hardening, not a sandbox.
"""
import fnmatch
import json
import os
import re
import sys

ROLES = {"orchestrator", "frontend-dev", "backend-dev", "reviewer", "tester"}
TASKS = ".blackboard/tasks/"
STOP = " Do not retry or work around it. Write the request to `## Open Questions` or `## Approvals Needed` in your task file and stop."
PROTECTED = {"AGENTS.md", "CLAUDE.md", ".gitignore"}
MANIFESTS = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "poetry.lock", "uv.lock",
    "Pipfile", "Pipfile.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "composer.json", "composer.lock", "Gemfile", "Gemfile.lock",
}
INFRA_GLOBS = [".github/*", ".gitlab-ci.yml", "Jenkinsfile", "Dockerfile*", "docker-compose*",
               ".env*", "*.tf", "k8s/*", "helm/*", "terraform/*"]
DEFAULT_TEST_GLOBS = ["*.test.*", "*.spec.*", "test_*.py", "*_test.py", "*_test.go", "*/__tests__/*", "__tests__/*"]


def deny(role, why):
    sys.stderr.write("BLOCKED (%s): %s.%s\n" % (role, why, STOP))
    sys.exit(2)


def ask(why):
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "ask",
                                      "permissionDecisionReason": why}}, sys.stdout)
    sys.exit(0)


def blank_quotes(cmd):
    pattern = r"'[^']*'|" + '"(?:[^"\\\\]|\\\\.)*"'
    return re.sub(pattern, lambda m: " " * len(m.group(0)), cmd, flags=re.S)


def bash_check(role, cmd):
    plain = blank_quotes(cmd)

    def has(p):
        return re.search(p, plain, re.I | re.S)

    # attribution: scan the original text, quotes included
    if re.search(r"git\s+commit|gh\s+pr\s+|gh\s+api", cmd, re.I) and (
            re.search(r"co-authored-by\s*:", cmd, re.I)
            or re.search(r"generated with\s*\[?claude|\U0001F916\s*generated", cmd, re.I)):
        deny(role, "AI attribution (Co-Authored-By / 'Generated with') is not allowed in commits, PRs, or comments")

    if has(r"\bgit\s+reset\s+--hard") or has(r"\bgit\s+checkout\b[^|;&]*\s--\s") or has(r"\bgit\s+clean\b"):
        deny(role, "discarding work (git reset --hard / checkout -- / clean) is not allowed")
    if has(r"\bgit\s+add\b[^|;&]*(\s-A\b|\s--all\b|\s-u\b|\s\.(\s|$))"):
        deny(role, "stage by explicit path (git add <paths>), never git add -A / . / -u (3e)")
    if re.search(r"\bgit\s+add\b[^|;&]*\.blackboard", cmd):
        deny(role, ".blackboard/ is git-ignored and must never be staged (3e)")
    if has(r"\bgh\s+pr\s+merge\b"):
        deny(role, "merging a PR is the human's")
    if (has(r"\bgh\s+pr\s+review\b[^|;&]*(--approve|\s-a\b|--request-changes|\s-r\b)")
            or re.search(r"event\W{1,5}(APPROVE|REQUEST_CHANGES)", cmd, re.I)):
        deny(role, "approving or requesting changes on a PR is the human's; use COMMENT only (3c)")
    if role != "reviewer" and (has(r"\bgh\s+pr\s+(review|comment)\b")
                               or has(r"\bgh\s+api\b[^|;&]*pulls/[^\s]*/(reviews|comments)")):
        deny(role, "only the Reviewer posts PR reviews and comments (3c)")
    if has(r"search\.py[^|;&]*--force"):
        deny(role, "ui-ux-pro-max --force is never allowed")

    if role == "reviewer":
        if (has(r"\bgit\s+(add|commit|apply|am|merge|cherry-pick|stash|switch|checkout|reset|restore|mv|pull)\b")
                or has(r"\b(sed|perl)\s+(-\w*i\b|--in-place)")
                or has(r"(?:^|[|;&(])\s*(?:sudo\s+)?(tee|mv|cp|touch|truncate|patch)\b")):
            deny(role, "the Reviewer is read-only (only its own task file may be written)")
        for target in re.findall(r"(?<![0-9&<>])>>?\s*(?![&>])([^\s;|&)]+)", plain):
            t = re.sub(r"^\./", "", target)
            if t != "/dev/null" and not t.startswith(TASKS):
                deny(role, "the Reviewer may redirect output only into .blackboard/tasks/")

    if has(r"\bgit\s+push\b[^|;&]*(--force|--force-with-lease|\s-f\b|\s\+)"):
        ask("force-push rewrites remote history and needs your approval")
    if has(r"\bgit\s+(rebase|filter-branch)\b") or has(r"\bgit\s+commit\b[^|;&]*--amend"):
        ask("rebase / amend rewrites history and needs your approval")
    if has(r"\bgit\s+push\b") or has(r"\bgh\s+(pr|repo)\s+create\b"):
        ask("push / PR creation needs your approval (Hard Rules)")
    if has(r"(?:^|[\s;&|(])(rm|rmdir|unlink)\s") or has(r"\bgit\s+rm\b"):
        ask("deleting files needs your approval (Hard Rules)")
    deps = [r"\b(npm|pnpm|yarn|bun)\s+(add|remove|uninstall|upgrade|update|up)\b",
            r"\b(npm|pnpm|bun)\s+(install|i)\s+[^-\s]", r"\bpip3?\s+install\b",
            r"\buv\s+(add|remove|pip\s+install)\b", r"\bpoetry\s+(add|remove|update)\b",
            r"\bgo\s+get\b", r"\bcargo\s+(add|remove|update)\b", r"\bcomposer\s+(require|remove|update)\b"]
    if any(has(d) for d in deps):
        ask("adding or changing dependencies needs your approval (Hard Rules)")
    if has(r"\b(alembic\s+(upgrade|downgrade|revision)|prisma\s+migrate|knex\s+migrate|rails\s+db:(migrate|rollback)"
           r"|flyway\s+migrate|manage\.py\s+(migrate|makemigrations))\b"):
        ask("schema / migration commands need your approval (Hard Rules)")
    if has(r"project_scaffolder\.py") or has(r"search\.py[^|;&]*--persist"):
        ask("scaffolding / --persist create files outside your scope and need your approval")


def rel_path(project, cwd, p):
    ap = p if os.path.isabs(p) else os.path.join(cwd or project, p)
    rel = os.path.relpath(os.path.realpath(ap), project)
    return None if rel == ".." or rel.startswith("../") else rel


def load_scope(project):
    try:
        with open(os.path.join(project, ".claude", "scope.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def dirs(scope, key):
    return [d.strip().strip("/") for d in scope.get(key, []) if d and "[" not in d]


def under(rel, ds):
    return any(d in ("", ".") or rel == d or rel.startswith(d + "/") for d in ds)


def is_test(rel, scope):
    base = os.path.basename(rel)
    for g in scope.get("test_globs", DEFAULT_TEST_GLOBS):
        if fnmatch.fnmatch(rel if "/" in g else base, g):
            return True
    return False


def is_infra(rel):
    base = os.path.basename(rel)
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(base, g) for g in INFRA_GLOBS)


def path_check(role, data):
    project = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    ti = data.get("tool_input") or {}
    p = ti.get("file_path") or ti.get("notebook_path")
    if not p:
        return
    rel = rel_path(project, data.get("cwd"), p)
    if rel is None:
        deny(role, "%s is outside the project" % p)
    if rel.startswith(".claude/") or rel in PROTECTED:
        deny(role, "%s is spec/config; only the human edits it" % rel)
    if rel.startswith(".blackboard/"):
        if rel.endswith(".template.md"):
            if role == "orchestrator":
                ask("editing a blackboard template changes every future goal")
            deny(role, "blackboard templates are edited by the Orchestrator with approval")
        if role == "orchestrator" or rel.startswith(TASKS):
            return
        deny(role, "BOARD.md and archive/ are written by the Orchestrator only")
    if role == "orchestrator":
        deny(role, "the Orchestrator does not write application code; create a task for a worker")
    if role == "reviewer":
        deny(role, "the Reviewer is read-only; send findings to the Owner via the Fix Loop")

    scope = load_scope(project)
    test = is_test(rel, scope) or under(rel, dirs(scope, "test_dirs"))
    migr = under(rel, dirs(scope, "migration_dirs"))
    if role == "tester":
        if not test:
            deny(role, "the Tester edits only test files; application code goes back to the Owner")
    else:
        key = "frontend_dirs" if role == "frontend-dev" else "backend_dirs"
        ds = dirs(scope, key)
        if not ds:
            deny(role, "no %s configured in .claude/scope.json" % key)
        if test:
            deny(role, "test files belong to the Tester; ask via Open Questions")
        if role == "backend-dev" and migr:
            ask("writing into the migrations directory needs your approval")
        if not under(rel, ds):
            deny(role, "%s is outside your scope (%s)" % (rel, ", ".join(ds)))
    base = os.path.basename(rel)
    if migr:
        ask("writing into the migrations directory needs your approval")
    if base in MANIFESTS:
        ask("dependency manifests change dependencies and need your approval")
    if is_infra(rel):
        ask("CI / infra / env files need your approval")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    kind = (data.get("agent_type") or "").lower()
    role = next((r for r in ROLES if kind == r or kind.endswith(":" + r) or kind.endswith("/" + r)), None)
    if role is None:
        sys.exit(0)
    tool = data.get("tool_name")
    if tool == "Bash":
        bash_check(role, (data.get("tool_input") or {}).get("command", ""))
    elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path_check(role, data)
    sys.exit(0)


if __name__ == "__main__":
    main()
