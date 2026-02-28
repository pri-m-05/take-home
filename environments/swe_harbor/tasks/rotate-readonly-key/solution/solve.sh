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

models_old = """    def dashboard_url(self) -> str | None:
        if not self.api_key_readonly:
            return None

        frag = urlencode({self.api_key_readonly: str(self)}, quote_via=quote)
        return reverse("hc-dashboard") + "#" + frag

    def checks_url(self, full: bool = True) -> str:
"""
models_new = """    def dashboard_url(self) -> str | None:
        if not self.api_key_readonly:
            return None

        frag = urlencode({self.api_key_readonly: str(self)}, quote_via=quote)
        return reverse("hc-dashboard") + "#" + frag

    def rotate_readonly_key(self) -> str:
        while True:
            candidate = token_urlsafe(24)
            if len(candidate) == 32 and candidate != self.api_key:
                self.api_key_readonly = candidate
                self.save(update_fields=["api_key_readonly"])
                return candidate

    def checks_url(self, full: bool = True) -> str:
"""
if "def rotate_readonly_key(self) -> str:" not in models:
    if models_old not in models:
        raise SystemExit("Could not find insertion point in hc/accounts/models.py")
    models = models.replace(models_old, models_new)

views_old = """@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""
views_new = """@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""
# Keep checks untouched; insert new view before it
insert_before = """@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""
new_view = """@cors("POST")
@csrf_exempt
@authorize
def rotate_readonly_key(request: ApiRequest) -> HttpResponse:
    new_key = request.project.rotate_readonly_key()
    return JsonResponse({"api_key_readonly": new_key})


@csrf_exempt
@cors("GET", "POST")
def checks(request: HttpRequest) -> HttpResponse:
"""
if "def rotate_readonly_key(request: ApiRequest) -> HttpResponse:" not in views:
    if insert_before not in views:
        raise SystemExit("Could not find insertion point in hc/api/views.py")
    views = views.replace(insert_before, new_view)

urls_old = """api_urls = [
    path("checks/", views.checks),
    path("checks/<uuid:code>", views.single, name="hc-api-single"),
"""
urls_new = """api_urls = [
    path("checks/", views.checks),
    path("project/rotate_readonly_key/", views.rotate_readonly_key),
    path("checks/<uuid:code>", views.single, name="hc-api-single"),
"""
if 'path("project/rotate_readonly_key/", views.rotate_readonly_key),' not in urls:
    if urls_old not in urls:
        raise SystemExit("Could not find insertion point in hc/api/urls.py")
    urls = urls.replace(urls_old, urls_new)

models_path.write_text(models)
views_path.write_text(views)
urls_path.write_text(urls)
PY
