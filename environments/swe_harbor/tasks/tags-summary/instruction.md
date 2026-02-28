# Tags Summary API Endpoint

The Healthchecks codebase is at `/app/`.

Implement a new API endpoint that returns per-tag check counts for the authenticated project.

## What to build

Add a new endpoint:

- `GET /api/v3/tags/`

This endpoint should authenticate using either the project's write API key or read-only API key and return tag counts in this JSON format:

    {"tags": [{"tag": "prod", "n_checks": 2}, {"tag": "db", "n_checks": 1}]}

## Required behavior

- use the authenticated project only
- count each tag at most once per check
  - for example, a check with tags `"prod prod db"` contributes:
    - `prod: +1`
    - `db: +1`
- ignore blank / whitespace-only tags
- sort results alphabetically by tag, case-insensitively
- support optional query parameter `q`
  - case-insensitive prefix filter on tag name
  - example: `?q=pr` matches `prod` and `preprod`
- support optional query parameter `min_checks`
  - integer
  - only return tags whose count is at least `min_checks`
  - invalid values should return HTTP 400 with JSON:
    - `{"error": "min_checks must be a non-negative integer"}`

## Required changes

### 1. Project helper (`/app/hc/accounts/models.py`)

Add a helper method on `Project` that returns the tag summary for that project.

Requirements:

- aggregate tags across the project's checks
- count each tag only once per check
- support:
  - `q` prefix filtering
  - `min_checks` filtering
- return a sorted list of dicts in the shape:

    [{"tag": "prod", "n_checks": 2}, ...]

### 2. API view (`/app/hc/api/views.py`)

Add a new view for `GET /api/v3/tags/`.

Requirements:

- use `@csrf_exempt`
- use `@cors("GET")`
- use `@authorize_read`
- return JSON in the expected shape
- validate `min_checks`

Behavior requirements:

- missing API key → `401`
- wrong API key → `401`
- `POST` to this endpoint should return `405`
- `OPTIONS` should return `204`
- read-only API keys must work

### 3. URL route (`/app/hc/api/urls.py`)

Add the new route to the shared `api_urls` list so it is available under:

- `/api/v1/`
- `/api/v2/`
- `/api/v3/`

## Constraints

- don't modify existing tests
- don't add new dependencies
- follow the existing error response conventions
- no database migration is required
