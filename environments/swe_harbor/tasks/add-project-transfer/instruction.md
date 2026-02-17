# Add Check Transfer API

The Healthchecks codebase is at `/app/`. It's a Django app for monitoring cron jobs.

## What to build

Add an API endpoint for transferring a check from one project to another, with a log of past transfers.

## 1. `TransferLog` model (`/app/hc/api/models.py`)

New model (add after the `Flip` model) to record transfer history:

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="transfers"` |
| `from_project` | `ForeignKey` to `Project` | `on_delete=models.SET_NULL, null=True, related_name="+"` |
| `to_project` | `ForeignKey` to `Project` | `on_delete=models.SET_NULL, null=True, related_name="+"` |
| `created` | `DateTimeField` | `default=now` |
| `transferred_by` | `CharField` | `max_length=200, blank=True` — email of the API key owner |

Add `to_dict()` returning:
```python
{
    "uuid": str(self.code),
    "check": str(self.owner.code),
    "from_project": str(self.from_project.code) if self.from_project else None,
    "to_project": str(self.to_project.code) if self.to_project else None,
    "created": isostring(self.created),
    "transferred_by": self.transferred_by,
}
```

`Meta` class: `ordering = ["-created"]`.

## 2. Migration (`/app/hc/api/migrations/`)

Generate with `python manage.py makemigrations api --name transferlog`.

## 3. `Check.transfer()` method (`/app/hc/api/models.py`)

Add `transfer(self, target_project, transferred_by="")` that does these steps, all inside a `transaction.atomic()` block with `select_for_update()` on the check (same pattern as `ping()` and `lock_and_delete()`):

1. **Validate capacity** — call `target_project.num_checks_available()`, raise `ValueError("target project has no checks available")` if `<= 0`.
2. **Log the transfer** — create a `TransferLog` with `from_project=self.project`, `to_project=target_project`.
3. **Move the check** — set `self.project = target_project`.
4. **Reassign channels** — `self.channel_set.clear()`, then `self.channel_set.set(Channel.objects.filter(project=target_project))`.
5. **Reset alert state** — set `status="new"`, clear `last_start`, `last_ping`, `alert_after`, `last_duration`, set `n_pings=0`.
6. **Clean up old data** — delete all `Ping` and `Flip` objects for this check.
7. **Save** the check.

## 4. API views (`/app/hc/api/views.py`)

### `POST /api/v3/checks/<uuid:code>/transfer/`

Transfer a check to another project.

- Use `@authorize` (write key required)
- JSON body:
  - `project` (required): UUID string of the target project
  - `target_api_key` (required): write API key for the target project
- Authorization:
  - The request's `api_key` authenticates the source project (handled by `@authorize`)
  - `target_api_key` in the body must match the target project's `api_key`
  - `403` with `{"error": "not authorized for target project"}` if missing or wrong
- Validation:
  - `400` with `{"error": "missing project"}` if `project` not provided
  - `400` with `{"error": "invalid project uuid"}` if not a valid UUID
  - `404` if target project doesn't exist
  - `400` with `{"error": "cannot transfer to same project"}` if source == target
  - `400` with `{"error": "target project has no checks available"}` if at capacity
- On success: return the check's `to_dict()` with status `200`

### `GET /api/v3/checks/<uuid:code>/transfers/`

List transfer history for a check.

- Use `@authorize_read`
- Returns `{"transfers": [...]}`
- `403` if wrong project, `404` if check doesn't exist

Decorate `check_transfer` with `@cors("POST")`, `@csrf_exempt`, and `@authorize`. Decorate `check_transfers` with `@cors("GET")`, `@csrf_exempt`, and `@authorize_read`.

## 5. URL routes (`/app/hc/api/urls.py`)

Add to the `api_urls` list:

```python
path("checks/<uuid:code>/transfer/", views.check_transfer, name="hc-api-transfer"),
path("checks/<uuid:code>/transfers/", views.check_transfers, name="hc-api-transfers"),
```

## 6. `Check.to_dict()` (`/app/hc/api/models.py`)

Add `"transfers_count"` (integer) to the dict.

## Constraints

- Don't modify existing tests
- The transfer must be atomic — if any step fails, nothing gets committed
- Follow existing patterns for decorators, error responses, etc.
- Import `Project` from `hc.accounts.models` (already imported in views.py)
