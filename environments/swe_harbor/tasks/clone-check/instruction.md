# Clone Check API Endpoint

The Healthchecks codebase is at `/app/`.

Implement a new API endpoint that clones an existing check within the authenticated project.

## What to build

Add a new endpoint:

- `POST /api/v3/checks/<uuid>/clone`

This endpoint should:

- authenticate using the existing write API key
- locate the source check by UUID
- verify the source check belongs to the authenticated project
- create a new check in the same project
- copy configuration fields from the source check
- reset runtime/state fields on the clone
- copy the source check's assigned channels
- return HTTP 201 with the cloned check as JSON using the existing API representation

## Allowed request body fields

The request body may optionally include any of:

- `name`
- `slug`
- `tags`

These override the cloned values.

## Required behavior

### Authentication / permissions

- missing API key → `401`
- wrong API key → `401`
- read-only API key must not work
- source check in a different project → `403`
- nonexistent source check → `404`

### Method behavior

- `GET` to this endpoint should return `405`
- `OPTIONS` should return `204`

### Validation

Validate the optional JSON fields using the same style as the existing API:

- `name` must be a string, max length 100
- `slug` must be a string matching `^[a-z0-9-_]*$`
- `tags` must be a string, max length 500

Invalid input should return HTTP 400 with the existing JSON validation error style.

### Check limit

If the authenticated project owner is at the check limit, cloning should return `403`.

### Slug behavior

If the resulting slug would collide with an existing check in the same project:

- first collision → append `-copy`
- second collision → append `-copy-2`
- third collision → append `-copy-3`
- and so on

Examples:

- `alpha` → `alpha-copy`
- `alpha` again → `alpha-copy-2`

If no slug override is provided, start from the source check's slug.
If the source check has no slug, derive one from the resulting name using Django's `slugify`.
If the resulting slug is blank, allow it to remain blank.

### What to copy

Copy configuration-ish fields from the source check, including:

- `name`
- `slug`
- `tags`
- `desc`
- `kind`
- `timeout`
- `grace`
- `schedule`
- `tz`
- `filter_subject`
- `filter_body`
- `start_kw`
- `success_kw`
- `failure_kw`
- `methods`
- `manual_resume`

### What to reset

Reset runtime/state fields on the clone, including:

- `status` → `"new"`
- `n_pings` → `0`
- `last_ping` → `null`
- `last_start` → `null`
- `last_start_rid` → `null`
- `last_duration` → `null`
- `has_confirmation_link` → `false`
- `alert_after` → `null`

### Channels

Copy all channel assignments from the source check to the clone.

## Required changes

### 1. Check helper (`/app/hc/api/models.py`)

Add helper logic on `Check` to:

- generate a non-conflicting slug inside the same project
- clone a check with optional overrides
- copy channels
- reset runtime fields

### 2. API view (`/app/hc/api/views.py`)

Add a new view for:

- `POST /api/v3/checks/<uuid>/clone`

Requirements:

- use `@csrf_exempt`
- use `@cors("POST")`
- use `@authorize`
- validate the request body
- enforce project ownership
- enforce check limit
- return HTTP 201 with the cloned check JSON

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