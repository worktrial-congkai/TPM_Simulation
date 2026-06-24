# PM Simulation

A CLI-only Python simulation of a PM's first week at a small-to-medium SaaS company. The system evaluates **agent strategy**: different policy personas complete the same scenario at different simulated times with different outcomes.

**Stack:** Python 3.9+, sqlite3, Click, Rich, pytest

## What gets tested

The core loop under evaluation:

- Discover blockers (especially hidden root causes)
- Resolve stakeholder conflicts
- Prioritize tradeoffs and document decisions
- Keep the launch moving (vendor escalation, meetings, status updates)

Reviewers clone the repo, run `reset` → `run` → `eval`, and inspect terminal output plus run artifacts. No web UI. No manual driving mode.

## Quick start

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pm-sim scenario reset first-week-pm
pm-sim run --scenario first-week-pm --agent triage_first
pm-sim eval first-week-pm --run-id <run-id>
pm-sim eval first-week-pm --compare-agents
pytest
```

## Example scenario: `first-week-pm` (`scenarios/first-week-pm/scenario.yaml`)

**"First Week — Risky Feature Launch"** at Acme SaaS. Launch target: Friday 6 PM.

- **PROJ-17** (API integration) is blocked — OAuth vendor scope issue, but the task list only shows a vague "integration issue"
- **PROJ-22** (design sign-off) is blocked until a requirements meeting is held
- **Jordan** (enterprise customer) emails asking for out-of-scope analytics dashboard
- **Sam** (eng lead) emails pressuring for the launch date
- Exec expects a briefing by Day 3
- Information is scattered across tasks, `#eng-launch`, DMs, emails, and meetings — it must be discovered

## Agent personas

Four built-in personas under `scenarios/first-week-pm/agents/` compare different PM strategies:


| Persona         | Strategy emphasis                      | Expected outcome (seed 42)                   |
| --------------- | -------------------------------------- | -------------------------------------------- |
| `triage_first`  | Tasks → blocker DM → vendor → meetings | Wed ~11 AM launch, on-time (10), rubric ~7.5 |
| `inbox_first`   | Read all comms before triaging tasks   | Wed ~11 PM launch, slipped (7), rubric ~5.5  |
| `meeting_first` | Schedule requirements sync early       | Wed ~11 AM launch, on-time (10), rubric ~6.7 |
| `spam_ping`     | Message everyone, skip triage          | Launch fails, rubric ~0.5                    |


Compare all personas at once:

```sh
pm-sim eval first-week-pm --compare-agents
```

## CLI reference


| Command                                             | Purpose                                         |
| --------------------------------------------------- | ----------------------------------------------- |
| `pm-sim scenario reset <id>`                        | Seed a fresh world into `data/sim.db`           |
| `pm-sim run --scenario <id> --agent <persona>`      | Run an agent persona to completion or turn cap  |
| `pm-sim eval <id> [--run-id <id>]`                  | Print rubric report + strategy metrics          |
| `pm-sim eval <id> --compare-agents [--max-turns N]` | Reset, run all personas, print comparison table |
| `pm-sim run show --run-id <id>`                     | Print the turn log for a run                    |
| `pm-sim events log --run-id <id> [--json]`          | Print the action log for a run                  |


## Run artifacts

Each run writes artifacts to `data/runs/<run-id>/`:


| File              | Contents                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `turn.log`        | Per-turn observation, action, and result blocks (consecutive identical turns collapse into one ranged entry) |
| `timeline.txt`    | Agent ↔ coworker/world interaction timeline                                                                  |
| `action_log.json` | Structured audit trail of agent actions                                                                      |
| `eval.txt`        | Full rubric report (text)                                                                                    |
| `eval.json`       | Full rubric report (JSON)                                                                                    |


**Example run** (`first-week-pm` / `triage_first`, seed 42): `data/runs/21049cfc-8c6e-42a0-82c6-3305223062b1/`

[turn.log](data/runs/21049cfc-8c6e-42a0-82c6-3305223062b1/turn.log), [timeline.txt](data/runs/21049cfc-8c6e-42a0-82c6-3305223062b1/timeline.txt), [eval.txt](data/runs/21049cfc-8c6e-42a0-82c6-3305223062b1/eval.txt)

```sh
pm-sim run show --run-id 21049cfc-8c6e-42a0-82c6-3305223062b1
pm-sim events log --run-id 21049cfc-8c6e-42a0-82c6-3305223062b1
pm-sim eval first-week-pm --run-id 21049cfc-8c6e-42a0-82c6-3305223062b1
```





## Evaluation

`pm-sim eval` scores a run against the scenario rubric (`scenarios/first-week-pm/eval_rubric.yaml`):


| Component                | Weight | What it measures                                                |
| ------------------------ | ------ | --------------------------------------------------------------- |
| Blocker discovery        | 35%    | Found the OAuth root cause on time, without excessive chat spam |
| Stakeholder alignment    | 20%    | Tradeoff meeting held with eng and product after scope conflict |
| Project outcome          | 35%    | Launch on time, delayed with scope cut, or failed               |
| Communication discipline | 10%    | No excessive messaging without progress                         |


**Headline metric:** `launch_sim_datetime` (when the launch milestone completes)

**Strategy metrics:** launch time, time to blocker known, vendor escalated, critical path clear, tradeoff decision, launch slip days, turn counts, and tool usage (chat, email, meeting).

Example `pm-sim eval` output (`triage_first`, run `21049cfc-8c6e-42a0-82c6-3305223062b1`):

```text
Component                 Score  Weight
Blocker discovery         10.0/10     35%
Stakeholder alignment     10.0/10     20%
Project outcome           10.0/10     35%
Communication discipline  10.0/10     10%
────────────────────────────────────────
Total                    10.0/10

Strategy metrics:
  launch_sim_datetime:      Wed 11:11 AM
  time_to_blocker_known:    Mon 9:59 AM
  time_to_vendor_escalated: Mon 10:11 AM
  time_to_critical_path_clear: Wed 1:11 AM
  time_to_tradeoff_decision: Mon 10:14 AM
  launch_slipped_days:      0
  total_turns:              2259
  total_tool_count:         32
  chat_tool_count:          5
  email_tool_count:         21
  meeting_tool_count:       2
```

`--compare-agents` output:

```text
Persona          launch_completed     blocker_found    turns    rubric
----------------------------------------------------------------------
inbox_first      Wed 12:54 PM (+1 slip) Mon 11:42 AM     2963     8.1
meeting_first    Wed 11:09 AM         Mon 9:57 AM      2967     8.0
spam_ping        null                 null             3104     0.8
triage_first     Wed 11:11 AM         Mon 9:59 AM      2871    10.0

Rubric components (/10):
Persona           Blocker discovery  Stakeholder alignment  Project outcome  Communication discipline
-----------------------------------------------------------------------------------------------------
inbox_first                     7.6                   10.0              7.0                      10.0
meeting_first                  10.0                    0.0             10.0                      10.0
spam_ping                       0.0                    0.0              0.0                       7.5
triage_first                   10.0                   10.0             10.0                      10.0
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — run loop, event queue, agent/NPC/eval layers
- [docs/scenario-authoring.md](docs/scenario-authoring.md) — how to author scenario packages

## Repo layout

```
pm-sim/
  README.md
  pyproject.toml
  docs/
    architecture.md
    scenario-authoring.md
  src/pm_sim/
    cli/           # reset, run, eval, show, events log
    sim/           # run_loop, clock, event queue, handlers
    agent/         # observation, conditions, policies, actions
    tools/         # chat, email, calendar, meeting, task, doc (internal)
    npcs/          # policy templates, resolver, cooperation gates
    scenario/      # validate, load helpers
    eval/          # rubric, metrics, compare-agents
    display/       # turn logs, interaction timeline, score tables
  scenarios/first-week-pm/
    scenario.yaml
    coworkers.yaml
    policy_templates.yaml
    message_templates.yaml
    eval_rubric.yaml
    agents/
  data/            # sim.db, runs/ (gitignored)
  tests/
```

