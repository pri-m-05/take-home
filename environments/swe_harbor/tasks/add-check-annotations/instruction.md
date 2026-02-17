# Add Check Annotations

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add an annotations feature to the REST API so users can attach timestamped notes to checks (e.g. "deployed v2.0", "server maintenance window").

## 1. `Annotation` model (`/app/hc/api/models.py`)

New model with these fields:

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="annotations"` |
| `created` | `DateTimeField` | `default=now` |
| `summary` | `CharField` | `max_length=200` |
| `detail` | `TextField` | `blank=True, default=""` |
| `tag` | `CharField` | `max_length=50, blank=True, default=""` |

Add `to_dict()` returning: `uuid`, `created` (ISO 8601, no microseconds), `summary`, `detail`, `tag`.

`Meta` class: `ordering = ["-created"]`.

## 2. Migration (`/app/hc/api/migrations/`)

Generate with `python manage.py makemigrations api`.

## 3. API endpoints (`/app/hc/api/views.py`)

### `POST /api/v3/checks/<uuid:code>/annotations/`

Create an annotation.

- Use `@authorize` (write key required)
- JSON body: `summary` (required, string, max 200), `detail` (optional string), `tag` (optional string, max 50)
- Validate that `detail` and `tag` are strings if provided (return `400` if not)
- Validate `summary` is present and non-empty (after stripping whitespace)
- Return the annotation JSON with status `201`
- `400` for validation errors (with `{"error": "..."}`)
- `403` if check is in a different project
- `404` if check doesn't exist
- Max 100 annotations per check. Return `403` with `{"error": "too many annotations"}` if at limit

### `GET /api/v3/checks/<uuid:code>/annotations/`

List annotations for a check.

- Use `@authorize_read`
- Returns `{"annotations": [...]}`, newest first
- Optional query params:
  - `tag` — exact match filter
  - `start` — ISO 8601 datetime, annotations created >= this time
  - `end` — ISO 8601 datetime, annotations created < this time
- `403` if wrong project, `404` if check doesn't exist

Wire these up with a dispatcher called `check_annotations` that sends GET to the list handler and POST to the create handler. Decorate with `@csrf_exempt` and `@cors("GET", "POST")`.

## 4. URL routes (`/app/hc/api/urls.py`)

Add to the `api_urls` list (works across v1/v2/v3 automatically):

```
path("checks/<uuid:code>/annotations/", views.check_annotations, name="hc-api-annotations"),
```

## 5. `Check.to_dict()` (`/app/hc/api/models.py`)

Add `"annotations_count"` (integer) to the dict.

## 6. `Check.prune()` (`/app/hc/api/models.py`)

When pruning, also delete annotations older than the oldest retained ping. Add after the flip pruning:

```python
self.annotations.filter(created__lt=ping.created).delete()
```

## Constraints

- Don't modify existing tests
- Annotation limit is 100 per check
- Use `isostring()` for datetime formatting (already in the codebase)
- Follow existing patterns for decorators, error responses, etc.
