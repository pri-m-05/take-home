#!/bin/bash
# TODO: Write the reference solution.
# This script runs inside the container at /app against the Healthchecks codebase.
# It should produce the correct solution that passes all tests.
#
# Common patterns:
#   - Append to a file:     cat >> /app/hc/api/models.py << 'EOF' ... EOF
#   - Patch a file inline:  python3 -c "..." (read, replace, write)
#   - Run migrations:       cd /app && python manage.py makemigrations api && python manage.py migrate
#   - Install a package:    pip install some-package
#!/bin/bash
set -e
cd /app

python3 <<'PY'
from pathlib import Path

models_path = Path("/app/hc/accounts/models.py")
views_path = Path("/app/hc/api/views.py")
urls_path = Path("/app/hc/api/urls.py")

models = models_path.read_text()
views = views_path.read_text()
urls = urls_path.read_text()

# --- hc/accounts/models.py ---
models_anchor = """    def checks_url(self, full: bool = True) -> str:
"""
models_insert = """    def tags_summary(self, q: str = "", min_checks: int = 1) -> list[dict[str, int | str]]:
        counts: dict[str, int] = {}
        prefix = q.lower()

        for check in self.check_set.all().only("tags"):
            for tag in set(check.tags_list()):
                if prefix and not tag.lower().startswith(prefix):
                    continue
                counts[tag] = counts.get(tag, 0) + 1

        result = [
            {"tag": tag, "n_checks": n}
            for tag, n in counts.items()
            if n >= min_checks
        ]
        result.sort(key=lambda item: (str(item["tag"]).lower(), str(item["tag"])))
        return result

    def checks_url(self, full: bool = True) -> str:
"""

if "def tags_summary(self, q: str = \"\", min_checks: int = 1)" not in models:
    if models_anchor not in models:
        raise SystemExit("Could not find insertion point in hc/accounts/models.py")
    models = models.replace(models_anchor, models_insert)

# --- hc/api/views.py ---
views_anchor = """@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""
views_insert = """@cors("GET")
@csrf_exempt
@authorize_read
def tags(request: ApiRequest) -> JsonResponse:
    raw = request.GET.get("min_checks", "")
    if raw == "":
        min_checks = 1
    else:
        try:
            min_checks = int(raw)
        except ValueError:
            return JsonResponse(
                {"error": "min_checks must be a non-negative integer"},
                status=400,
            )
        if min_checks < 0:
            return JsonResponse(
                {"error": "min_checks must be a non-negative integer"},
                status=400,
            )

    q = request.GET.get("q", "").strip()
    return JsonResponse({"tags": request.project.tags_summary(q=q, min_checks=min_checks)})


@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""

if "def tags(request: ApiRequest) -> JsonResponse:" not in views:
    if views_anchor not in views:
        raise SystemExit("Could not find insertion point in hc/api/views.py")
    views = views.replace(views_anchor, views_insert)

# --- hc/api/urls.py ---
urls_anchor = """api_urls = [
    path("checks/", views.checks),
    path("checks/<uuid:code>", views.single, name="hc-api-single"),
"""
urls_insert = """api_urls = [
    path("checks/", views.checks),
    path("tags/", views.tags),
    path("checks/<uuid:code>", views.single, name="hc-api-single"),
"""

if 'path("tags/", views.tags),' not in urls:
    if urls_anchor not in urls:
        raise SystemExit("Could not find insertion point in hc/api/urls.py")
    urls = urls.replace(urls_anchor, urls_insert)

models_path.write_text(models)
views_path.write_text(views)
urls_path.write_text(urls)
PY
