# Design V2 Design

This document defines the next official `Design` stage for `coco-flow`.

It is intentionally aligned with the current `Input -> Refine -> Design -> Plan -> Code -> Archive` workflow and with the `Refine` v2 pattern of:

- controller prepares stable template files
- agent fills structured artifacts
- verifier checks consistency
- markdown is a human-readable derivative, not the only source of truth

## Executive Summary

- `Design` is a standalone stage between `Refine` and `Plan`.
- `Design` owns repo semantics for the first time.
- `Design` must not be implemented as prompt-only freeform JSON generation.
- `Design` should reuse the `Refine` pattern: controller-built templates plus agent-filled artifacts.
- Repo binding is **optional user-provided prior knowledge**, not a mandatory prerequisite.
- If the user already attached repos, `Design` skips repo discovery, but it does **not** skip repo-role judgment.
- If more than one repo needs deep exploration, repo exploration must run **in parallel**.
- Parallel exploration must use `AGENT_MODE` / `run_agent(...)`, not readonly explorer mode.
- Change points must not be hard-routed to repos before evidence exists. The system should use **soft assignment**, not irreversible routing.
- `design.md` should be generated from structured artifacts through a template-driven agent flow, with a deterministic fallback renderer only as backup.

## Goals

`Refine` answers: what is the request really asking for?

`Plan` answers: how should execution be ordered and validated?

`Design` sits in the middle and answers:

1. What engineering design conclusions should be drawn from the refined request?
2. Which repos really matter for this task?
3. What role does each repo play?
4. What are the main system changes, dependencies, critical flows, and risk boundaries?
5. What stable structured outputs should downstream `Plan` consume?

In other words, `Design` is responsible for system-level understanding and repo-level adjudication, not execution sequencing.

## Non-Goals

`Design` should not:

- produce the final execution breakdown for implementation
- decide the detailed task order for coding
- turn directly into repo-level work items
- silently expand scope beyond the refined request
- treat user-provided repos as unquestionable truth

## Stage Positioning

The intended responsibility split is:

1. `Input`
   - capture source content, supplement, and optional attached repos
2. `Refine`
   - clarify the request without relying on repo semantics
3. `Design`
   - formalize repo binding, system boundaries, and design conclusions
4. `Plan`
   - turn design conclusions into execution tasks and order
5. `Code`
   - execute by repo
6. `Archive`
   - summarize and close the task

Short version:

- `Refine`: what to do
- `Design`: why this system/repo split is correct
- `Plan`: what to do first, next, and how to verify

## Input Contract

`Design` consumes a `Design Bundle`, not raw task history.

### Required Inputs

The minimum required inputs are:

1. `prd-refined.md`
2. `repos.json`
3. task title

The task title should come from:

- `input.json.title`, otherwise
- `task.json.title`

### Recommended Inputs

These inputs are strongly recommended and should be treated as first-class upstream context:

1. `refine-intent.json`
2. `refine-knowledge-selection.json`
3. `refine-knowledge-read.md`
4. `input.json`

### Input Reading Rules

1. `prd-refined.md` is the only request baseline for `Design`.
2. `refine-intent.json` is guidance, not a replacement for refined content.
3. `refine-knowledge-read.md` provides inherited stable rules and terminology, not new product facts.
4. `repos.json` before `Design` means attached repo candidates, not final in-scope repos.
5. Repo research is grounding evidence, not business truth.

### Inputs That Must Not Become the Main Baseline

These may exist for provenance or fallback, but they must not become the main truth source for `Design` once `prd-refined.md` exists:

- `prd.source.md`
- `source.json`
- raw prompts or pre-refine fragments

## Repo Semantics in Design

This is the most important part of the stage.

Repo-related information should be split into three layers:

1. attached repos
2. design repo binding
3. runtime repo state

These are not the same thing.

### 1. Attached Repos

Repos attached before `Design` are only:

- a user-provided hint
- an allowed search space
- an optional acceleration path

They do **not** yet mean:

- these repos are definitely in scope
- these repos are definitely primary
- these repos already have assigned responsibilities

### 2. Design Repo Binding

Formal repo binding must be produced by `Design`.

It should answer, for each candidate repo:

1. Is it in scope?
2. Is it `primary`, `supporting`, `reference`, or effectively excluded?
3. Which change points does it serve?
4. What responsibility does it carry?
5. What boundaries should constrain its change scope?
6. What dependencies or coordination relationships does it have with other repos?

Recommended artifact:

- `design-repo-binding.json`

### 3. Runtime Repo State

`repos.json` should continue to exist because later stages need runtime state such as:

- repo status
- branch
- worktree
- commit

But `repos.json` should no longer be the only repo-truth file.

Recommended model:

- `design-repo-binding.json` is the formal design-time conclusion
- `repos.json` is the runtime state file
- `Design` may sync selected binding fields back into `repos.json`

## Optional User-Provided Repo Binding

Repo binding should be treated as an **optional prior**.

Two paths should be supported.

### Path A: User Did Not Attach Repos

The engine must:

1. infer candidate repos
2. shortlist repos
3. deeply explore shortlisted repos
4. adjudicate final repo binding

### Path B: User Already Attached Repos

The engine should:

1. skip repo discovery
2. treat attached repos as the explicit exploration set
3. still perform repo-role judgment and change-point adjudication
4. still allow some attached repos to end up as weakly-related or out-of-scope

Important rule:

User-provided repos only skip **repo discovery**.

They do **not** skip:

- change point extraction
- repo-role judgment
- repo binding adjudication

## The Main Risk: Misrouting Change Points

This is the main correctness risk in the whole stage.

Suppose:

- change point 1 really belongs to repo A
- change point 2 really belongs to repo B

If the system hard-routes change point 1 to repo B before enough evidence exists, the parallel exploration phase can become misleading and wasteful.

Therefore, `Design` must **not** use hard routing before evidence exists.

## Soft Assignment Before Parallel Exploration

Before repo exploration runs in parallel, the engine should create a **soft assignment** between change points and repos.

This step exists to focus exploration, not to make irreversible decisions.

### What Soft Assignment Means

For each change point, the engine should assign:

- `primary_candidate`
- `secondary_candidates`
- optionally `unlikely` or `unknown`

Example:

- change point 1
  - primary candidate: repo A
  - secondary candidate: repo B
- change point 2
  - primary candidate: repo B
  - secondary candidate: repo A

This means:

- repo A explores change point 1 deeply
- repo B still sees change point 1 as a secondary check
- no change point is silently excluded too early

### Why Soft Assignment Is Necessary

Without this step:

- every repo receives the entire request as equal-priority work
- all agents repeat the same broad search
- repo-role evidence becomes noisy

With hard assignment:

- one wrong early guess can poison the whole exploration chain

Soft assignment is the middle ground:

- exploration focus exists
- correction is still allowed

## Parallel Repo Exploration

Parallel repo exploration is mandatory when the deep-exploration repo count is greater than one.

### Hard Rules

1. If repo deep exploration count is `> 1`, exploration must run in parallel.
2. Parallel repo exploration must use `AGENT_MODE` via `run_agent(...)`.
3. It must not use readonly explorer mode as the primary implementation.
4. Each repo agent should receive:
   - global request background
   - the full refined context
   - the repo-specific soft assignment brief
   - permission to challenge the assignment

### What Each Repo Agent Must Answer

Each repo exploration result should explicitly include:

1. which change points are likely served by this repo
2. which change points are not likely served by this repo
3. candidate dirs and files
4. responsibility hints
5. dependency hints
6. evidence and counter-evidence
7. confidence

Recommended artifact shape inside `design-research.json`:

```json
{
  "mode": "llm_parallel",
  "prefilter": {
    "parallel": true,
    "candidate_repo_ids": ["repo_a", "repo_b"],
    "skipped_repo_ids": [],
    "scores": [
      {
        "repo_id": "repo_a",
        "score": 12,
        "reasons": ["matched terms", "candidate files"]
      }
    ]
  },
  "repos": [
    {
      "repo_id": "repo_a",
      "repo_path": "/path/to/repo_a",
      "selected_for_exploration": true,
      "explored": true,
      "exploration_mode": "llm",
      "decision": "in_scope_candidate",
      "role_hint": "primary",
      "serves_change_points": [1],
      "summary": "repo_a is the main candidate for change point 1",
      "matched_terms": ["auction card"],
      "candidate_dirs": ["app/explain_card"],
      "candidate_files": ["app/explain_card/render_handler.go"],
      "dependencies": [],
      "parallelizable_with": ["repo_b"],
      "evidence": ["matched explain card entrypoint"],
      "notes": ["this repo likely owns the UI-facing change"],
      "confidence": "high"
    }
  ]
}
```

## Repo Binding Adjudication

Repo binding adjudication happens **after** research, not before.

This step should use:

- refined request
- inherited refine knowledge
- change points
- repo exploration results

Its job is to produce the formal decision.

The key rule is:

**initial soft assignment is not evidence; it is only search guidance**

Final adjudication should rely on:

- direct repo evidence
- cross-repo comparison
- contradiction handling
- confidence-based escalation

## Reliability Strategy

To avoid major misjudgments, the engine should follow these rules.

### 1. No Single-Point Routing

Never let one early model guess irreversibly decide a change point to repo mapping.

### 2. Global Context + Repo-Focused Brief

Every repo agent should receive:

- global context
- local priority hints

not local hints alone

### 3. Explicit Negative Judgments

Repo exploration must be allowed to say:

- this change point probably does not belong here
- this repo is only supporting
- another repo likely owns the main change

### 4. Confidence-Based Overlap

If initial change-point-to-repo confidence is low, the engine should deliberately overlap exploration:

- multiple repos inspect the same change point

This costs more, but is much cheaper than a bad early exclusion.

### 5. Final Cross-Check

The final judge should compare repo claims, not read them independently.

The system should prefer:

- evidence convergence
- explicit contradiction
- transparent uncertainty

over confident but unsupported routing.

## Output Contract

`Design` outputs two classes of artifacts.

### Machine-Readable Source-of-Truth Artifacts

These are the formal outputs downstream systems should consume:

1. `design-research.json`
2. `design-knowledge-brief.md`
3. `design-repo-binding.json`
4. `design-sections.json`
5. `design-verify.json`
6. `design-result.json`

### Human-Readable Output

The human-facing design document remains:

- `design.md`

But it is not the only truth source.

`design.md` should be derived from structured artifacts.

## `design-sections.json`

This artifact should contain the stable design structure consumed by the markdown generator and later by `Plan`.

Recommended sections:

1. `system_change_points`
2. `solution_overview`
3. `system_changes`
4. `system_dependencies`
5. `critical_flows`
6. `protocol_changes`
7. `storage_config_changes`
8. `experiment_changes`
9. `qa_inputs`
10. `staffing_estimate`

## `design.md`

`design.md` should be generated by:

1. controller creates a fixed markdown template
2. agent fills the template using structured artifacts
3. verifier checks consistency

It should not default to:

- fully deterministic string concatenation as the main path
- freeform prompt-only markdown generation

Fallback deterministic rendering is still acceptable if the native path fails.

## Engine Architecture

`Design` should mirror the `Refine` file structure.

Recommended structure:

```text
src/coco_flow/engines/design/
├── __init__.py
├── source.py
├── knowledge.py
├── research.py
├── binding.py
├── generate.py
├── logging.py
├── models.py
└── pipeline.py

src/coco_flow/prompts/design/
├── __init__.py
├── shared.py
├── research.py
├── repo_binding.py
├── generate.py
└── verify.py
```

## Orchestration Flow

The intended orchestration is:

1. Prepare design input bundle
   - no LLM
2. Inherit and normalize refine knowledge
   - lightweight LLM optional
3. Extract change points and soft assignment baseline
   - LLM
4. Repo discovery
   - no LLM if repos already attached
   - lightweight heuristics otherwise
5. Parallel repo exploration
   - LLM
   - `AGENT_MODE`
6. Aggregate research
   - no LLM
7. Repo binding adjudication
   - LLM
8. Generate design sections
   - LLM or deterministic synthesis depending on executor mode
9. Generate `design.md`
   - template-driven agent
10. Verify
   - agent verifier
11. Persist result
   - no LLM

## LLM vs Non-LLM Split

### Non-LLM Steps

- read task artifacts
- normalize input bundle
- deterministic repo prefilter
- aggregate parallel exploration results
- persist artifacts
- deterministic markdown fallback

### LLM Steps

- change point extraction
- soft assignment generation
- repo exploration
- repo binding adjudication
- markdown generation
- verification

## Suggested Artifact Lifecycle

At the end of `Design`, the system should have:

- `design.md`
- `design.log`
- `design-research.json`
- `design-knowledge-brief.md`
- `design-repo-binding.json`
- `design-sections.json`
- `design-verify.json`
- `design-result.json`

And optionally synced runtime hints inside `repos.json`, such as:

- `in_scope`
- `design_role`
- `depends_on`
- `candidate_dirs`
- `candidate_files`

## UI Semantics

Repo binding should not be treated as a hard blocker for `Design`.

Recommended UI semantics:

- `Generate Design` should still exist even when no repos are attached.
- `Bind Repos (Optional)` should be a separate action.
- If repos are attached:
  - skip repo discovery
  - still run soft assignment and repo-role adjudication
- If repos are not attached:
  - run repo discovery first

This means repo binding is a user acceleration path, not a mandatory gate.

## Incremental Implementation Plan

The engine feels complex because it includes both search-space control and correctness control.

The implementation should therefore be incremental.

### Phase 1: Structural Separation

Goal:

- split `Design` out of the old `plan` front half
- create dedicated engine and prompt folders
- generate standalone `design-*` artifacts

### Phase 2: Parallel Repo Research

Goal:

- add deterministic prefilter
- add `AGENT_MODE` repo exploration
- aggregate `design-research.json`

### Phase 3: Soft Assignment and Reliability

Goal:

- add explicit change point extraction
- add soft assignment before parallel exploration
- add confidence-aware overlap
- make repo exploration prompts challengeable, not rigid

### Phase 4: Formal Repo Binding

Goal:

- make `design-repo-binding.json` the main repo design artifact
- sync selected fields back to `repos.json`

### Phase 5: Downstream Simplification

Goal:

- make `Plan` consume `Design` conclusions directly
- remove duplicated repo-role reasoning from `Plan`

## Current Session Prompt

You can directly use this sentence in a new session:

> Current Input and Refine have already been refactored. Refine now uses a controller-builds-template plus agent-fills-structured-artifacts pattern. Continue designing the Design stage with maximum reuse of that pattern, do not choose a prompt-only JSON-first path, and move formal repo binding forward into Design.

