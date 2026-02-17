# Traverse: SWE Harbor Take-Home Assignment

## Codebase Landscape

This repository is a fork of [Verifiers](https://github.com/PrimeIntellect-ai/verifiers), a framework by Prime Intellect for training and evaluating AI coding agents with reinforcement learning. The top-level structure:

```
take-home/
├── verifiers/              # The core Verifiers framework (library code — don't modify)
│   ├── envs/               # Built-in environment types (SingleTurnEnv, HarborEnv, etc.)
│   ├── rubrics/            # Reward/scoring infrastructure
│   ├── rl/                 # Reinforcement learning trainers
│   └── ...
├── environments/
│   └── swe_harbor/         # ← YOUR WORKING DIRECTORY
│       ├── swe_harbor.py   # Environment class that loads and runs tasks
│       ├── pyproject.toml  # Project config and dependencies
│       ├── environment/    # Shared Docker environment (Healthchecks app)
│       │   ├── Dockerfile  # Builds the base image
│       │   └── app/        # Healthchecks codebase (pinned at v3.6)
│       └── tasks/          # ← Where you create tasks
│           ├── _template/                # Starter template to copy
│           ├── add-check-annotations/    # Example: add feature (annotations)
│           └── add-project-transfer/     # Example: add feature (check transfer)
└── README.md               # ← You are here
```

You only need to work inside `environments/swe_harbor/tasks/`. Everything else is supporting infrastructure.

## The Shared Codebase

All tasks operate against a **single shared codebase**: [Healthchecks](https://github.com/healthchecks/healthchecks) (v3.6), an open-source cron job monitoring service built with Python/Django.

The codebase lives in `environment/app/` and is baked into a single Docker image that all tasks share. Tasks are lightweight — just instruction + solution + tests — with no per-task `environment/` directory.

## The Environment

**SweHarborEnv** (`environments/swe_harbor/swe_harbor.py`) is a Harbor-format environment that evaluates AI coding agents. Here's what happens when a task runs:

1. The framework builds and starts a Docker container from the **shared** `environment/Dockerfile`.
2. The task instruction (`instruction.md`) is mounted at `/task/instruction.md` inside the container.
3. A tool-use agent script is uploaded into the container. The agent has four tools: `bash`, `read_file`, `write_file`, and `str_replace`. It reads the instruction and works to solve the task.
4. When the agent finishes (or times out), `tests/test.sh` runs inside the container.
5. The test runner executes `test_solution.py` with pytest and writes a reward — `1` (all tests pass) or `0` (any test fails) — to `/logs/verifier/reward.txt`.

The agent never sees the tests. It only sees `instruction.md`.

## Your Task

Create **1-2 original software engineering tasks** in Harbor format. Place each task in its own directory under `environments/swe_harbor/tasks/`.

Each task directory must contain these files:

| File | Purpose |
|------|---------|
| `task.toml` | Task metadata — difficulty level, timeouts |
| `instruction.md` | The problem statement the agent sees |
| `solution/solve.sh` | Reference solution — a bash script that produces the correct answer |
| `tests/test_solution.py` | Pytest test cases that verify correctness |
| `tests/test.sh` | Test runner that executes pytest and writes the reward file |

**Requirements:**

1. The reference solution (`solve.sh`) must pass all tests (reward = 1)
2. Tests must **fail** without the solution applied (reward = 0)
3. Tests should catch incorrect or incomplete solutions, not just the happy path
4. At least one task should involve **multiple files**

### Getting Started

1. **Fork this repo** — click "Fork" on GitHub, then clone your fork
2. **Study the examples** — `environments/swe_harbor/tasks/add-check-annotations/` and `environments/swe_harbor/tasks/add-project-transfer/` are the best references for the kind of complexity we're looking for
3. **Browse the Healthchecks codebase** — explore `environments/swe_harbor/environment/app/hc/` to find areas for tasks. See the [Healthchecks GitHub](https://github.com/healthchecks/healthchecks) for documentation
4. **Copy the template** — `cp -r environments/swe_harbor/tasks/_template environments/swe_harbor/tasks/your-task-name`
5. **Fill in each file** — follow the TODO comments in the template
6. **Test locally** — verify your task end-to-end with Docker (see below)

### Task Design Guidelines

We're building tasks to evaluate **long-horizon agent capabilities** — multi-step problems that require planning, navigating multiple files, and composing several pieces of work together. Think of tasks that a junior engineer might spend a day on, not something solved in a single function.

**Good task types:**

| Type | Example |
|------|---------|
| Add a feature | New API endpoint with model, view, URL, and tests |
| Debug across a codebase | Multiple bugs spread across files that interact with each other |
| Extend an existing system | Add significant new features to the Healthchecks app |
| Refactor + fix + extend | Combination tasks that require understanding before changing |

**What makes a good long-horizon task:**

- **Multiple files** — the agent must create or modify 3+ files
- **Interdependencies** — changes in one file affect the correctness of another
- **Planning required** — the agent can't just bang out code linearly; it needs to reason about structure
- **Realistic complexity** — resembles real engineering work, not toy problems
- **Incremental progress** — partial solutions are possible but won't pass all tests

**Avoid:**

- Leetcode/competitive programming puzzles
- Tasks requiring internet access (containers are isolated)
- Subjective tasks with no deterministic pass/fail
- Trivially passable tests (agent should not be able to stumble into a solution)
- Single-function tasks that don't require multi-step reasoning

**Scope:** Tasks should be **hard enough that current frontier models don't trivially solve them**. Aim for problems that require 1-2 hours of focused work from a skilled engineer — multiple implementation steps, cross-file coordination, and meaningful test coverage (~20-40 tests).

## Running the Environment

### Prerequisites

- **Docker** — must be installed and running
- **`OPENROUTER_API_KEY`** — only needed for full framework runs (not Docker-only quick verification). Copy `.env.example` to `.env` and fill in your key:
  ```bash
  cp environments/swe_harbor/.env.example environments/swe_harbor/.env
  # then edit .env with your OpenRouter API key
  ```

### Quick Verification (Docker Only)

The fastest way to test a task. Run these commands from the `environments/swe_harbor/` directory.

```bash
cd environments/swe_harbor
```

**Step 1: Build the shared Docker image (once)**

```bash
docker build -t swe-harbor environment/
```

**Step 2: Run with your solution (expect reward = `1`)**

```bash
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/solution:/solution \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

**Step 3: Run without your solution (expect reward = `0`)**

```bash
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

If Step 2 prints `1` and Step 3 prints `0`, your task works correctly. If both print `1`, your tests aren't actually checking the solution.

**Concrete example** using the included `add-check-annotations` task:

```bash
# Build the shared image
docker build -t swe-harbor environment/

# With solution (should print 1)
docker run --rm \
    -v $(pwd)/tasks/add-check-annotations/solution:/solution \
    -v $(pwd)/tasks/add-check-annotations/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"

# Without solution (should print 0)
docker run --rm \
    -v $(pwd)/tasks/add-check-annotations/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

### Full Framework Run (Optional)

To run tasks through the full Verifiers pipeline with an actual AI agent, you need additional setup.

**Install dependencies:**

```bash
# From the repo root
uv add verifiers
prime env install swe_harbor --path ./environments/swe_harbor
```

**Run an evaluation:**

```bash
prime eval run swe_harbor -m gpt-4
```

This spins up the full agent loop: the model reads `instruction.md`, uses its tools to solve the task, and then tests are run automatically.

## Harbor Format Reference

### `task.toml`

```toml
version = "1.0"

[metadata]
author_name = "Your Name"
author_email = "you@example.com"
difficulty = "easy"        # easy | medium | hard
category = "programming"
tags = ["python", "django", "rest-api"]

[verifier]
timeout_sec = 180.0        # Max time for test execution

[agent]
timeout_sec = 900.0        # Max time for the agent to work
```

Note: no `[environment]` section is needed — the shared Docker image is used for all tasks.

### `instruction.md`

The problem statement the agent receives. Be specific about:

- What files to create or modify (paths under `/app/`)
- Expected function signatures, class interfaces, or API behavior
- Input/output examples where helpful
- Constraints or requirements

The agent works against the Healthchecks codebase at `/app/`.

### `solution/solve.sh`

A bash script that produces the correct solution. Runs inside the container at `/app`. It can write files (using heredocs), apply patches (with Python or `sed`), run migrations, or run commands. Must be deterministic and pass all tests.

### `tests/test.sh`

Entry point for test execution. Standard pattern:

```bash
#!/bin/bash
cd /app
pip install pytest > /dev/null 2>&1
mkdir -p /logs/verifier

# Run migrations in case the solution created new ones
python manage.py migrate --run-syncdb > /dev/null 2>&1

PYTHONPATH=/app DJANGO_SETTINGS_MODULE=hc.settings pytest /tests/test_solution.py -v 2>&1
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Must write `1` (pass) or `0` (fail) to `/logs/verifier/reward.txt`.

### `tests/test_solution.py`

Standard pytest test file using Django's test infrastructure. Extend `BaseTestCase` from `hc.test` for pre-built users, projects, and API keys. Test the happy path, edge cases, and error conditions. Keep tests independent with no shared mutable state. Aim for 20-40 tests.
