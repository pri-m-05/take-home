# Add Check Transfer API

You are working on [Healthchecks](https://github.com/healthchecks/healthchecks), an open-source cron job monitoring service built with Django. The codebase is located at `/app/`.

## Overview

Add an API endpoint that allows users to **transfer a check from one project to another**. This is a common request from users who reorganize their monitoring setup. The transfer must handle channel reassignment, preserve ping and flip history, and enforce proper authorization.

## Requirements

### 1. Add a `TransferLog` model (`/app/hc/api/models.py`)

Create a new model to record transfer history. Add it after the existing `Flip` model.

| Field | Type | Details |
|-------|------|---------|
| `code` | `UUIDField` | `default=uuid.uuid4, editable=False, unique=True` |
| `owner` | `ForeignKey` to `Check` | `on_delete=models.CASCADE, related_name="transfers"` |
| `from_project` | `ForeignKey` to `Project` | `on_delete=models.SET_NULL, null=True, related_name="+"` |
| `to_project` | `ForeignKey` to `Project` | `on_delete=models.SET_NULL, null=True, related_name="+"` |
| `created` | `DateTimeField` | `default=now` |
| `transferred_by` | `CharField` | `max_length=200, blank=True` — records the email of the API key owner |

Add a `to_dict()` method that returns:
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

Add `class Meta` with `ordering = ["-created"]`.

### 2. Create a migration

Generate a migration: `python manage.py makemigrations api --name transferlog`

### 3. Add a `transfer()` method to `Check` (`/app/hc/api/models.py`)

Add a method `transfer(self, target_project, transferred_by="")` that:

1. **Validates** the target project has capacity — call `target_project.num_checks_available()` and raise `ValueError("target project has no checks available")` if `<= 0`.
2. **Records the transfer** — create a `TransferLog` entry with `from_project=self.project`, `to_project=target_project`.
3. **Moves the check** — update `self.project` to `target_project`.
4. **Reassigns channels** — clear existing channel assignments (`self.channel_set.clear()`) and assign all channels from the target project (`self.channel_set.set(Channel.objects.filter(project=target_project))`).
5. **Resets alert state** — set `self.status` to `"new"`, clear `last_start`, `last_ping`, `alert_after`, `last_duration`, set `n_pings` to `0`.
6. **Cleans up old data** — delete all `Ping` objects for this check, and delete all `Flip` objects for this check.
7. **Saves** the check.

The entire operation should be wrapped in `transaction.atomic()` with `select_for_update()` on the check (same pattern as `ping()` and `lock_and_delete()`).

### 4. Add API views (`/app/hc/api/views.py`)

#### `POST /api/v3/checks/<uuid:code>/transfer/` — Transfer a check

- Requires write API key (use `@authorize` decorator)
- Accepts JSON body with:
  - `project` (required): UUID string of the target project
  - `target_api_key` (required): write API key for the target project (used to verify authorization)
- **Authorization rules:**
  - The `api_key` in the request authenticates the **source** project (handled by the `@authorize` decorator).
  - A separate `target_api_key` field in the JSON body must match the target project's `api_key` to verify write access to the target project.
  - Return `403` with `{"error": "not authorized for target project"}` if `target_api_key` is missing or doesn't match the target project's `api_key`
- **Validation:**
  - Return `400` with `{"error": "missing project"}` if `project` is not provided
  - Return `400` with `{"error": "invalid project uuid"}` if `project` is not a valid UUID
  - Return `404` if the target project doesn't exist
  - Return `400` with `{"error": "cannot transfer to same project"}` if source == target
  - Return `400` with `{"error": "target project has no checks available"}` if target is at capacity
- **On success:** Return the check's `to_dict()` representation with status `200`

#### `GET /api/v3/checks/<uuid:code>/transfers/` — List transfer history

- Requires read API key (use `@authorize_read` decorator)
- Returns `{"transfers": [...]}` with transfer log entries for this check
- Returns `403` if check belongs to a different project
- Returns `404` if check doesn't exist

Create a dispatcher view `check_transfer` for the transfer endpoint (POST only) with `@csrf_exempt` and `@cors("POST")`.

Create a separate view `check_transfers` for the transfer history endpoint (GET only) with `@csrf_exempt` and `@cors("GET")`.

### 5. Add URL routes (`/app/hc/api/urls.py`)

Add URL patterns in the `api_urls` list:

```python
path("checks/<uuid:code>/transfer/", views.check_transfer, name="hc-api-transfer"),
path("checks/<uuid:code>/transfers/", views.check_transfers, name="hc-api-transfers"),
```

### 6. Update `Check.to_dict()` (`/app/hc/api/models.py`)

Add a `"transfers_count"` key to the dictionary returned by `Check.to_dict()`. Its value should be the number of `TransferLog` entries for this check (an integer).

## Constraints

- Do NOT modify any existing tests
- The transfer should be atomic — if any step fails, no changes should be committed
- Follow existing code patterns for decorators, error handling, and JSON responses
- Import `Project` from `hc.accounts.models` (it's already imported in views.py)
