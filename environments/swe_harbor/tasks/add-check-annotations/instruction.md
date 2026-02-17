# Add Check Annotations Feature

You are working on [Healthchecks](https://github.com/healthchecks/healthchecks), an open-source cron job monitoring service built with Django. The codebase is located at `/app/`.

## Overview

Add an **annotations** feature that lets users attach timestamped notes to their health checks via the REST API. Annotations are useful for documenting deployments, incidents, maintenance events, or any context that helps explain check behavior.

## Requirements

### 1. Create the `Annotation` model (`/app/hc/api/models.py`)

Add a new Django model called `Annotation` with the following fields:

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="annotations"` |
| `created` | `DateTimeField` | `default=now` |
| `summary` | `CharField` | `max_length=200` |
| `detail` | `TextField` | `blank=True, default=""` |
| `tag` | `CharField` | `max_length=50, blank=True, default=""` — categorize annotations (e.g., "deploy", "incident", "maintenance") |

Add a `to_dict()` method that returns a dictionary with keys: `uuid`, `created` (ISO 8601 string with no microseconds), `summary`, `detail`, `tag`.

Add a `Meta` class with `ordering = ["-created"]`.

### 2. Create a migration (`/app/hc/api/migrations/`)

Create a Django migration file for the new model. You can generate it using `python manage.py makemigrations api`.

### 3. Add API endpoints (`/app/hc/api/views.py`)

Add two new view functions:

#### `POST /api/v3/checks/<uuid:code>/annotations/` — Create annotation

- Requires write API key (use the `@authorize` decorator)
- Accepts JSON body with fields: `summary` (required, string, max 200 chars), `detail` (optional string), `tag` (optional string, max 50 chars)
- Validates that `summary` is present and non-empty
- Returns the annotation as JSON with status `201`
- Returns `400` with `{"error": "..."}` for validation errors
- Returns `403` if the check belongs to a different project than the API key
- Returns `404` if the check doesn't exist
- Limit: a check can have at most **100 annotations**. If the limit is reached, return `403` with `{"error": "too many annotations"}`

#### `GET /api/v3/checks/<uuid:code>/annotations/` — List annotations

- Requires read API key (use the `@authorize_read` decorator)
- Returns `{"annotations": [...]}` sorted by creation date descending (newest first)
- Supports optional query parameters:
  - `tag` — filter by annotation tag (exact match)
  - `start` — ISO 8601 datetime, only return annotations created on or after this time
  - `end` — ISO 8601 datetime, only return annotations created before this time
- Returns `403` if the check belongs to a different project
- Returns `404` if the check doesn't exist

Create a dispatcher view function called `check_annotations` that routes `GET` to the list handler and `POST` to the create handler. Decorate it with `@csrf_exempt` and `@cors("GET", "POST")`.

### 4. Add URL routes (`/app/hc/api/urls.py`)

Register the new endpoint under all three API versions. Add a URL pattern for each version (v1, v2, v3):

```
path("checks/<uuid:code>/annotations/", views.check_annotations),
```

The name for the route should be `"hc-api-annotations"` (only needed on one of them).

### 5. Update `Check.to_dict()` (`/app/hc/api/models.py`)

Add an `"annotations_count"` key to the dictionary returned by `Check.to_dict()`. Its value should be the number of annotations attached to that check (an integer).

### 6. Update `Check.prune()` (`/app/hc/api/models.py`)

Modify the `prune()` method so that when a check is pruned, any annotations older than the oldest retained ping are also deleted. Add this after the existing notification pruning logic:

```python
self.annotations.filter(created__lt=ping.created).delete()
```

## Constraints

- Do NOT modify any existing tests
- The annotation limit per check is 100
- All datetime strings in API responses should use ISO 8601 format with no microseconds (use the existing `isostring()` helper)
- Follow the existing code patterns for decorators, error handling, and JSON responses
