# SWE Harbor

## Repo Structure

```
take-home/
├── verifiers/              # Core Verifiers framework (don't modify)
│   ├── envs/
│   ├── rubrics/
│   ├── rl/
│   └── ...
├── environments/
│   └── swe_harbor/         # ← YOU ARE HERE
│       ├── swe_harbor.py   # Environment class
│       ├── pyproject.toml
│       ├── environment/    # Shared Docker environment
│       │   ├── Dockerfile
│       │   └── app/        # Healthchecks v3.6 codebase
│       └── tasks/
│           ├── _template/
│           ├── add-check-annotations/
│           └── add-project-transfer/
└── README.md
```

## Shared Codebase

All tasks run against [Healthchecks](https://github.com/healthchecks/healthchecks) v3.6, a Django-based cron monitoring service. The code lives in `environment/app/` and gets baked into a single Docker image.

The main files you'll want to look at:

| Module | Description |
|--------|-------------|
| `hc/api/models.py` | Check, Channel, Ping, Flip, Notification models |
| `hc/api/views.py` | REST API endpoints |
| `hc/api/urls.py` | URL routing |
| `hc/accounts/models.py` | Users, teams, profiles, projects |
| `hc/front/views.py` | Web UI views |
| `hc/lib/` | Shared utilities |

## How It Works

`SweHarborEnv` (in `swe_harbor.py`) runs tasks in Docker:

1. Container starts from `environment/Dockerfile`
2. `instruction.md` gets mounted in
3. An agent with bash/file tools reads the instruction and works on it
4. When done, `tests/test.sh` runs pytest and writes `1` or `0` to `/logs/verifier/reward.txt`

The agent only sees `instruction.md`, never the tests.

## Creating Tasks

Put each task in its own directory under `tasks/`. You need these files:

| File | What it is |
|------|------------|
| `task.toml` | Metadata and timeouts |
| `instruction.md` | Problem statement for the agent |
| `solution/solve.sh` | Reference solution |
| `tests/test_solution.py` | Pytest tests |
| `tests/test.sh` | Runs pytest, writes reward file |

Requirements:
1. `solve.sh` must pass all tests (reward = 1)
2. Tests must fail without the solution (reward = 0)
3. Tests should catch bad solutions, not just check the happy path
4. At least one task should touch multiple files

Start by copying the template: `cp -r tasks/_template tasks/your-task-name`

Look at `tasks/add-check-annotations/` and `tasks/add-project-transfer/` for examples.

### What makes a good task

We're testing whether an agent can handle real multi-step engineering work. Good tasks require reading existing code, planning across files, and making interdependent changes. Think "junior engineer's first day project", not "leetcode problem".

Aim for 3+ files touched, 20-40 tests, and enough complexity that partial solutions fail.

## Docker Verification

From this directory (`environments/swe_harbor/`):

**Build the image (once):**
```bash
docker build -t swe-harbor environment/
```

**Test with solution (should print `1`):**
```bash
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/solution:/solution \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

**Test without solution (should print `0`):**
```bash
docker run --rm \
    -v $(pwd)/tasks/TASK_NAME/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

If both print `1`, your tests aren't actually testing anything.

**Example:**
```bash
docker build -t swe-harbor environment/

docker run --rm \
    -v $(pwd)/tasks/add-check-annotations/solution:/solution \
    -v $(pwd)/tasks/add-check-annotations/tests:/tests \
    swe-harbor \
    bash -c "mkdir -p /logs/verifier && cd /app && bash /solution/solve.sh && bash /tests/test.sh && cat /logs/verifier/reward.txt"
```

## Full Framework Run (Optional)

```bash
# From repo root
uv add verifiers
prime env install swe_harbor --path ./environments/swe_harbor
prime eval run swe_harbor -m gpt-4
```

## test.sh Pattern

```bash
#!/bin/bash
cd /app
pip install pytest > /dev/null 2>&1
mkdir -p /logs/verifier

python manage.py migrate --run-syncdb > /dev/null 2>&1

PYTHONPATH=/app DJANGO_SETTINGS_MODULE=hc.settings pytest /tests/test_solution.py -v 2>&1
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```
