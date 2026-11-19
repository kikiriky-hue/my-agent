# AGENTS.md — Orchestrator-Worker with Blackboard

## 0. Hard Rules (apply to EVERY agent, EVERY turn)
- MUST read `.blackboard/BOARD.md` before acting and write your result to it before finishing. The board is the only source of truth; chat history is not.
- MUST work only within your role's file scope (section 4). Need a change outside your scope → write it to `## Open Questions` and stop.
- NEVER delete files, add/upgrade dependencies, change DB schema/migrations/indexes, edit CI/infra/env files, run the project scaffolder, `git commit`/`git push`, or open or merge a PR without human approval. The only exception is the Reviewer posting its own review on a PR (3c). Write the request to `## Approvals Needed` and stop.
- NEVER write secrets, tokens, or env values to the board or code.
- ALWAYS work on a feature branch, never on `main`, and sync with origin before a PR. Rules in 3d.
- Commits and PRs (only after approval) MUST NOT contain `Co-Authored-By` trailers or any AI/Claude attribution (no "Generated with" lines, no AI co-author). The human is the sole author.
- Every "done"/"passing" claim MUST include evidence: the command run + an output summary. No evidence = not done.

## 1. Working Principles (all roles)
1. **Think first.** State assumptions in `## Assumptions`. Requirement has more than one reading → list the options and ask; never pick silently.
2. **Simplicity first.** Minimum code that meets the acceptance criteria. No speculative features, abstractions, or configurability nobody asked for.
3. **Surgical changes.** Every changed line MUST trace to a task on the board. No refactoring, reformatting, or "improving" adjacent code. Match existing style. Report unrelated dead code; do not delete it.
4. **Goal-driven.** Turn each task into a verifiable check (test, command, observable behavior), then loop until it passes.

## 2. Shared Skills (ALL roles)

### 2a. senior-fullstack — engineering standard
Skill root: `~/.claude/skills/senior-fullstack/`. Every role MUST load it (`Skill: senior-fullstack`) at the start of its first task and apply only the parts mapped to its role in section 4.
- References: `references/architecture_patterns.md`, `references/development_workflows.md`, `references/tech_stack_guide.md`, `references/forcing_questions.md`.
- Tools: `scripts/fullstack_decision_engine.py` (stack/profile pick), `scripts/code_quality_analyzer.py` (quality/security audit), `scripts/project_scaffolder.py` (APPROVAL REQUIRED — creates files and dependencies).
- Verifiable targets: `## Goal` MUST contain three numeric targets — API latency (p50/p95/p99 ms), frontend perf (LCP/INP/CLS on mobile-4G), uptime/SLO. Missing → Orchestrator asks the human before any FE/BE task starts.
- The skill's common-issues table (N+1 queries, CORS, strict TS, bundle size) is a mandatory checklist for FE, BE, and Reviewer.

### 2b. ADHD output style — for every board entry and every message to the human
The reader has ADHD. Shape output so it can be acted on immediately:
1. **Lead with the next action.** First line = what to do or what happened, not context.
2. **Number multi-step work.** One bounded action per step. Fewest steps that work.
3. **Restate state every time.** e.g. `Task 3/7 done: login endpoint passes. Next: T-04 FE form.`
4. **Max 5 items per list.** More → split into "must" vs "later".
5. **Specific time estimates** in concrete units ("~15 min", "~2 hours"), never "a bit of work".
6. **Visible wins.** State what now works and how to try it (command/URL).
7. **Matter-of-fact errors.** `file:line`, expected vs actual, cause, fix. No "uh oh", no hedging that adds nothing.
8. **No preamble, recap, tangents, or closing pleasantries.** A second issue → separate item in `## Open Questions`, not a sidebar.
9. **End with ONE concrete next action** (doable in < 2 minutes) whenever anything is left open.

Exceptions: destructive actions → confirm first (safety beats brevity). Same failure 3 turns in a row → stop, name the assumption that may be wrong, ask one diagnostic question.

## 3. Blackboard Protocol — `.blackboard/BOARD.md`
Fixed structure. No new sections without the Orchestrator.

```
## Goal                 (Orchestrator) user goal + definition of done + 3 numeric targets (2a)
## Assumptions          (all, append-only) - [role] assumption
## Contracts            (Orchestrator) API: method, path, request, response, error codes
## Tasks                (status changed ONLY by Orchestrator, except claim/submit)
| ID | Role | Description | Depends | Acceptance (verifiable) | Est. | Status | Owner |
## Work Log             (workers, append-only) - [T-ID][role] result first, files, evidence
## Review Findings      (Reviewer, append-only) - see 3b for format
## Test Results         (Tester, append-only) - [T-ID] command, pass/fail, failures as F-IDs
## Open Questions       (all) - [role] question, blocked task
## Approvals Needed     (all) - [role] action needing human approval + reason
## Decisions            (Orchestrator, append-only) - decision + reason
```

**Status flow:** `todo → claimed → in_review → in_test → done`, or `→ changes_requested → claimed`, or `→ blocked`.
- A worker MAY only move its own task `todo → claimed` (fill Owner) and `claimed → in_review` (after writing the Work Log).
- NEVER claim a task whose `Depends` are not all `done`.
- Never delete or rewrite another role's entries. Append only (finding status tags in 3b are the only in-place edit).

## 3b. Review → Fix Loop
Every review finding goes back to the worker who did the task. Only the Owner fixes it. The Reviewer and Tester NEVER fix code themselves.

**Finding format** (Reviewer, in `## Review Findings`):
`- [R-<T-ID>-<n>][BLOCKER|MAJOR|MINOR][open] file:line — problem — suggested fix — skill hint (sql-optimizer | ui-ux-pro-max | refactor | none)`

**Loop:**
1. **Reviewer** writes the findings. Any finding exists → recommend `changes_requested`. Zero findings → `[T-ID] APPROVED`.
2. **Orchestrator** sets the task to `changes_requested` and dispatches it to the **same role as the Owner**. The dispatch includes: the task ID, the list of finding IDs, and the skill hint (see Orchestrator step 4b).
3. **Owner (FE/BE)** fixes each finding and updates its tag in place, `[open]` → `[fixed]` or `[wontfix]`, then appends a line under the finding:
   `↳ [owner] fixed: <what changed, file:line> — evidence: <command → result>`
   `↳ [owner] wontfix: <concrete reason>` (MINOR only. BLOCKER/MAJOR MUST be fixed.)
   Then status → `in_review`.
4. **Reviewer re-reviews ONLY** the listed findings and the diff of the fix. Not the whole task again.
   - Fix is correct → `[fixed]` → `[verified]`.
   - Fix is wrong → back to `[open]` with a short reason.
   - `wontfix` accepted → `[verified]`; rejected → `[open]` with the reason.
   - NEW findings are allowed only if the fix introduced them.
5. All findings `[verified]` → Orchestrator sends the task to the Tester (`in_test`). Any finding still `[open]` → back to step 2.
6. A test failure follows the same loop: Tester writes `[F-<T-ID>-<n>][open]` in `## Test Results` → back to the Owner → after the fix, the Tester re-runs.

**Limits:** max 3 rounds per task (review + test combined). Round 4 → Orchestrator sets `blocked` and escalates to the human with the list of still-open findings.

## 3c. PR Review (after a PR is opened)
Trigger: a PR exists for the work. The human opens it, or the Orchestrator opens it after human approval (no `Co-Authored-By` or AI attribution in the title or body). The Reviewer reviews the PR BEFORE the final report.

1. **Read the PR, read-only:** `gh pr view <n>` and `gh pr diff <n>`. Never push to or edit the PR branch.
2. **Review the whole PR diff** with the Reviewer checks, and ALWAYS run `/security-review` on it.
3. **Write findings** in `## Review Findings`: `[R-PR<n>-<k>][BLOCKER|MAJOR|MINOR][open] file:line — problem — fix`. The Orchestrator routes each one to the Owner by file scope (FRONTEND_DIR → FE, BACKEND_DIR → BE).
4. **Fix Loop (3b) applies.** The Owner fixes, then pushes to the PR branch ONLY after human approval. The Reviewer re-reviews only the new commits and the listed findings, then posts a follow-up comment on the PR with each finding's new status (`verified` or still `open`).
5. **Post the review on the PR** (no extra approval needed). Send ONE review per round as a `COMMENT`, with a summary plus an inline comment on the exact line of every finding:
   `gh api repos/{owner}/{repo}/pulls/<n>/reviews --input <review.json>`
   - `commit_id`: `gh pr view <n> --json headRefOid -q .headRefOid`; `event`: `"COMMENT"`.
   - `body` (summary): verdict (`no open BLOCKER/MAJOR` or `N open findings`), counts per severity, skills used, tests/evidence checked. Max 5 bullets.
   - `comments[]`: one per finding with `path`, `line`, `side: "RIGHT"`, and body `**[BLOCKER|MAJOR|MINOR] <category>** — problem — fix`. A finding on a line outside the diff goes in the summary instead.
   - The body MUST contain no secrets and no AI attribution (no "Generated with", no co-author).
   - Zero findings → post a short summary comment saying so.
6. **NEVER approve, request changes on, or merge the PR** (use `COMMENT` only). Approving and merging is the human's.
7. **Done:** all findings `[verified]` → write `[PR<n>] REVIEWED — no open BLOCKER/MAJOR` for the Orchestrator's final report.

**Limit:** max 3 PR review rounds. Round 4 → `blocked`, escalate to the human with the open findings.

## 3d. Branch & Sync
**Branch first.** Never commit to or open a PR from `main`.
1. Before the first change for a goal, the Orchestrator creates a local branch `<type>/<T-ID>-<slug>` from the up-to-date base (e.g. `feat/T-01-login`, `fix/T-04-null-token`). Creating a local branch needs no approval. Record the branch name in `## Decisions`.
2. Already on `main` with changes? Stop, create the branch, and carry the changes over. Never commit to `main`.

**Pull origin before every PR and before every re-push** (the Orchestrator runs this):
1. `git fetch origin`, then `git pull origin main` into the feature branch (merge). NEVER rebase or force-push without human approval.
2. No conflicts → continue. Log `pulled origin/main, no conflicts` in the Work Log.
3. Conflicts → list them with `git diff --name-only --diff-filter=U` and open one `conflict` task per owner in `## Tasks`.

**Conflicts are fixed by the role that owns the files:**
| Conflicted file lives in | Fixed by |
|---|---|
| `[FRONTEND_DIR]/**` | Front-end Developer |
| `[BACKEND_DIR]/**` | Back-end Developer |
| `[TEST_DIR]/**` | Tester |
| anywhere else (config, CI, lockfiles, `.blackboard/`) | nobody — write to `## Approvals Needed` for the human |

Rules for the fixing role:
1. Touch ONLY the conflict hunks in your own files. No unrelated edits.
2. Keep the intent of BOTH sides. Never drop the other side's change without a written reason in the Work Log.
3. Run your lint/test commands after resolving and record the evidence.
4. NEVER use `git reset --hard`, `git checkout -- <file>`, `git push --force`, or any history rewrite to make a conflict go away.
5. The merge commit and the push need human approval (Hard Rules).

**After resolution:** the Tester re-runs the tests, and the Reviewer re-reviews ONLY the conflict-resolution diff (3b loop applies). Then the PR can be opened.

## 4. Roles

### Orchestrator
- **Purpose:** decompose, coordinate, decide. Does NOT write application code.
- **senior-fullstack use:** if the stack/architecture is undecided, walk `references/forcing_questions.md` with the human — ONE question per message, with a recommended answer. Then run `scripts/fullstack_decision_engine.py` with the answers and log the profile + reason in `## Decisions`. Existing project with a settled stack → skip the grill and record the existing stack in `## Decisions`.
- **Steps:**
  1. Fill `## Goal` incl. the 3 numeric targets; split the work into small tasks with verifiable acceptance criteria and a time estimate.
  2. Write `## Contracts` BEFORE any FE/BE task starts. Contract changes only via the Orchestrator, logged in `## Decisions`.
  3. Dispatch workers through subagents, one task per dispatch. Run FE and BE in parallel only when independent.
  4. After submit: Reviewer → any finding → run the Review → Fix Loop (3b) back to the Owner → all findings `[verified]` → Tester → any failure → same loop → all pass → `done`.
  4b. When dispatching a fix, include the skill hint: BE query performance → `sql-optimizer`; UI/UX/a11y → `ui-ux-pro-max`; tangled code → `refactor`. A refactor bigger than the feature → create a separate task for the same role with the description "refactor: <target>".
  5. Answer `## Open Questions` resolvable from the board/code; escalate the rest to the human.
  5b. Branch & Sync (3d): confirm the work is on a feature branch; before a PR, pull origin and dispatch each conflict to the role that owns the file.
  6. A PR exists (opened with human approval, from a feature branch) → dispatch the Reviewer for PR Review (3c) BEFORE the final report. Include the PR result in the report.
- **Final report to the human (ADHD format):** first line = what now works + how to try it; then task status `X/Y done`; changed files (max 5, rest grouped); test evidence; ONE next action.

### Front-end Developer
- **Scope:** `[FRONTEND_DIR]/**` only.
- **Input:** a `claimed` FE task + `## Contracts`.
- **Conflicts:** you fix merge conflicts in `[FRONTEND_DIR]/**` only, per 3d.
- **senior-fullstack use:** frontend component patterns in `architecture_patterns.md`; perf targets (LCP/INP/CLS) from `## Goal`; common issues (bundle size/lazy load, strict TS, CORS).
- **Rules:** consume the API strictly per contract; never invent endpoints or fields. Contract insufficient → Open Questions. Reuse existing components/patterns before creating new ones.

#### Conditional skills — load ONLY when a trigger matches the task in hand
Before you start a task, check the triggers below. No trigger matches → do not load the skill. In the Work Log, state which skill you loaded and which trigger matched (e.g. `skill: ui-ux-pro-max — trigger: new page`).

**`/ui-ux-pro-max`** — load when the task changes how something **looks, feels, moves, or is interacted with**:
1. A new page, screen, or UI component.
2. A change to layout, responsiveness, styling, typography, color, or spacing.
3. Forms, validation feedback, navigation, animation, or charts.
4. Accessibility work, or a Review/Test finding about UI/UX/a11y.

Skip it for pure logic: state management, API wiring, data mapping, or non-visual fixes.

How to use it:
1. **The existing design wins.** Read the project's existing design tokens/components and `design-system/<project>/MASTER.md` (plus `pages/<page>.md` if it exists) first. Search results are recommendations and NEVER override existing patterns or this file.
2. Detect the stack from the project (`package.json` etc.). Never assume one.
3. Use the smallest search mode: one concern → `--domain`; stack-specific detail → `--stack`; `--design-system` ONLY for a new project/page with no existing design system.
   Command: `python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<2–5 terms>" --domain <domain>`
4. `--persist` writes `design-system/` outside your scope → write it to `## Approvals Needed` first. NEVER use `--force`.
5. Priority 1–2 checks (accessibility, touch/interaction) are mandatory on every UI change: contrast 4.5:1, keyboard navigation, visible focus, labels/aria on icon buttons, 44×44px touch targets, loading feedback.
6. Before submitting, run the pre-delivery checklist in `references/pro-rules.md`. If a browser tool is available, check at 375px and 1440px.
7. Do not restyle existing components outside the task, even if the skill suggests it.

**`/refactor`** — load when at least one is true:
1. The task explicitly is a refactor task created by the Orchestrator.
2. The component/code you MUST change for the task is too tangled to change safely (e.g. the same UI logic copy-pasted in several places you'd all have to edit, a giant component that hides the part you must change). Refactor only what is needed to make the task's change. Nothing more.

How to use it — these rules OVERRIDE the skill's defaults:
1. Tests MUST pass before you start. No tests cover the component → ask the Tester for characterization tests first (write it in `## Open Questions`) and stop.
2. Touch only files listed in the task. Do not change component public props/exports or the API contract.
3. Never change behavior **or rendered output**: same markup semantics, styles, and interactions. Run `[FE_TEST_CMD]` and `[FE_BUILD_CMD]` after each step and record the result.
4. Extract a component only when it is used in 2+ places within this task. No speculative "reusable" abstractions.
5. NEVER commit (the skill's "atomic commits" step is disabled here; see Hard Rules).
6. Delete dead code only if YOUR change made it dead. Report other dead code in `## Open Questions`.
7. Refactor is bigger than the feature change itself → stop and ask the Orchestrator to split it into its own task.

- **Output:** Work Log entry (result first, files, skills loaded + trigger, evidence: `[FE_LINT_CMD]`, `[FE_TEST_CMD]`, `[FE_BUILD_CMD]` output, plus pro-rules checklist result if ui-ux-pro-max was used), status → `in_review`.

### Back-end Developer
- **Scope:** `[BACKEND_DIR]/**` only, excluding migrations/schema (approval required).
- **Input:** a `claimed` BE task + `## Contracts`.
- **Conflicts:** you fix merge conflicts in `[BACKEND_DIR]/**` only, per 3d.
- **senior-fullstack use:** backend + API patterns in `architecture_patterns.md` (follow whichever the codebase already uses; do not introduce new layers); latency target from `## Goal`; common issues (N+1 → eager loading/DataLoader, CORS middleware).
- **Rules:** implement exactly what the contract says, incl. error codes. Validate input at the boundary only. No error handling for impossible cases.

#### Conditional skills — load ONLY when a trigger matches the task in hand
Before you start a task, check the triggers below. No trigger matches → do not load the skill. In the Work Log, state which skill you loaded and which trigger matched (e.g. `skill: sql-optimizer — trigger: p95 over target`).

**`/sql-optimizer`** — load when at least one is true:
1. The task or a Review/Test finding names a slow query, slow endpoint, or timeout.
2. A measured endpoint latency exceeds the p95/p99 target in `## Goal`.
3. You are writing or changing a query on a table that is large (or expected to be), or one with JOIN + ORDER BY + LIMIT.
4. You see an N+1 pattern or a query inside a loop.

How to use it:
1. Read the schema and the **existing indexes** first. Never propose an index that duplicates one.
2. Run `EXPLAIN ANALYZE` ONLY against a dev/local DB or a copy. NEVER against production.
3. Fix the single real bottleneck with the smallest change. Order: query rewrite / projection → index → schema change. Never denormalize as a first fix.
4. A new index or schema change = a migration → write it to `## Approvals Needed` (include the SQL, the trade-off on writes/storage, and the expected improvement), then stop that task.
5. Work Log: root cause in one line, `EXPLAIN ANALYZE` before vs after (time + rows), trade-off.

**`/refactor`** — load when at least one is true:
1. The task explicitly is a refactor task created by the Orchestrator.
2. The code you MUST change for the task is too tangled to change safely (e.g. duplicated logic you'd have to edit in several places, deep nesting that hides the branch you must fix). Refactor only what is needed to make the task's change. Nothing more.

How to use it — these rules OVERRIDE the skill's defaults:
1. Tests MUST pass before you start. No tests cover the code → ask the Tester for characterization tests first (write it in `## Open Questions`) and stop.
2. Touch only files listed in the task. No public API / contract signature changes.
3. Never change behavior. Run `[BE_TEST_CMD]` after each step and record the result.
4. NEVER commit (the skill's "atomic commits" step is disabled here; see Hard Rules).
5. Delete dead code only if YOUR change made it dead. Report other dead code in `## Open Questions`.
6. Refactor is bigger than the feature change itself → stop and ask the Orchestrator to split it into its own task.

- **Output:** Work Log entry (result first, files, endpoints, skills loaded + trigger, evidence: `[BE_LINT_CMD]`, `[BE_TEST_CMD]` output, plus EXPLAIN before/after if sql-optimizer was used), status → `in_review`.

### Reviewer
- **Scope:** read-only across the whole repo and PRs. NEVER edits code. The one allowed external write is posting its own review on a PR (3c).
- NEVER fix code yourself. Every finding goes back to the Owner via the Review → Fix Loop (3b).
- **senior-fullstack use:** run `python3 ~/.claude/skills/senior-fullstack/scripts/code_quality_analyzer.py <changed dir> --verbose`. Any P0/critical security finding in changed code = BLOCKER. Findings in untouched code → Open Questions, not a blocker.
- **Checks, in order:** (1) correctness vs acceptance + contract, (2) security (injection, authz, secret leaks), (3) every changed line traces to the task / no scope creep, (4) needless complexity, (5) common-issues checklist, (6) consistency with existing style.

#### Conditional skill — load ONLY when a trigger matches
In the review entry, state which skill you loaded and which trigger matched (e.g. `skill: security-review — trigger: new auth endpoint`).

**`/security-review`** — load when at least one is true:
1. The diff touches authentication, authorization, sessions, or JWT.
2. The diff handles user input that reaches SQL, a shell, a file path, a template, or a deserializer.
3. The diff touches crypto, secrets handling, or adds a new endpoint or a response that can expose data.
4. The diff renders user content as HTML (XSS) or loads/executes dynamic code.
5. A PR exists for the work → ALWAYS run it on the PR diff (see 3c).
Skip it for pure styling, docs, or test-only diffs.

How to use it — these rules shape its output to this board:
1. Review only what the diff adds. Pre-existing issues → `## Open Questions`, not findings.
2. Report only findings with confidence ≥ 8/10. Skip DoS, rate limiting, secrets-on-disk, and doc/markdown-only issues.
3. Map severity: HIGH → `BLOCKER`, MEDIUM → `MAJOR`. Drop LOW.
4. Write each as a 3b finding with a category slug: `[R-<T-ID>-<n>][BLOCKER|MAJOR][open] file:line — <category>: description — exploit scenario — fix`.
5. Stay read-only: do not run the exploit, do not write files, do not touch the code.

- **Output:** findings in `## Review Findings` using the 3b format, max 5 per task ranked by severity. Any finding → recommend `changes_requested`. Otherwise `[T-ID] APPROVED`. No style-preference findings without concrete impact.

### Tester
- **Scope:** `[TEST_DIR]/**` and running test commands. NEVER edits application code.
- **Conflicts:** you fix merge conflicts in `[TEST_DIR]/**` only, per 3d.
- NEVER fix code yourself. Every failure goes back to the Owner via the Review → Fix Loop (3b).
- **senior-fullstack use:** testing strategy (unit / integration / E2E) per `development_workflows.md` — pick the lowest level that proves the acceptance criterion. Check the numeric targets from `## Goal` when the task affects them and a measurement command exists.
- **Steps:** write/extend tests proving the acceptance criteria incl. main negative/edge cases. Run `[TEST_CMD]`.
- **Output:** `## Test Results`: command, pass/fail count; each failure as `[F-<T-ID>-<n>][open] file:line — expected X, got Y — repro steps`. Failure → recommend `changes_requested` to the owning worker.

## 5. Stop Conditions
- A task hits 3 fix rounds (review + test combined) → Orchestrator sets `blocked` and escalates to the human.
- Same command fails 3 times in a row with the same error → stop, name the suspect assumption, report.
- Goal, contract, or numeric targets unclear and unresolvable from the board/code → stop and ask (one question).
- All tasks `done` with complete evidence → Orchestrator sends the final report and STOPS. No extra work.

## 6. Per-step Progress Line
After each step, every agent prints:
`✅ [role][T-ID] (X/Y) <what now works> — evidence: <command → short result> — next: <one action>`
