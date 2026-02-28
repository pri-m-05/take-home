# Rotate Read-only API Key

The Healthchecks codebase is at `/app/`.

Implement a new API endpoint that rotates the authenticated project's read-only API key.

## What to build

Add a new endpoint:

- `POST /api/v3/project/rotate_readonly_key/`

This endpoint should:

- authenticate using the existing write API key
- generate a fresh 32-character read-only API key
- save it to `Project.api_key_readonly`
- return HTTP 200 with JSON:

    {"api_key_readonly": "<new 32 character key>"}

## 1. Project helper (`/app/hc/accounts/models.py`)

Add a helper method on `Project` for rotating the read-only key.

Requirements:

- generate a new 32-character key
- save it to `api_key_readonly`
- return the new key
- each call must produce a new key

## 2. API view (`/app/hc/api/views.py`)

Add a new view for `POST /api/v3/project/rotate_readonly_key/`.

Use the same patterns as the existing API views.

Requirements:

- use `@csrf_exempt`
- use `@cors("POST")`
- use `@authorize`
- do not manually re-implement API key parsing
- on success, return JSON with the new read-only key

Behavior requirements:

- missing API key → `401`
- wrong API key → `401`
- invalid JSON body → `400`
- `GET` to this endpoint should return `405`
- rotating the key should only affect the authenticated project

## 3. URL route (`/app/hc/api/urls.py`)

Add the new route to the shared `api_urls` list so it is available under:

- `/api/v1/`
- `/api/v2/`
- `/api/v3/`

## Constraints

- don't modify existing tests
- don't add new dependencies
- follow the existing error response conventions
- no database migration is required
