#!/bin/bash
set -e
cd /app

python3 <<'PY'
from pathlib import Path

models_path = Path("/app/hc/api/models.py")
views_path = Path("/app/hc/api/views.py")
urls_path = Path("/app/hc/api/urls.py")

models = models_path.read_text()
views = views_path.read_text()
urls = urls_path.read_text()

# --- hc/api/models.py ---
if "from django.utils.text import slugify" not in models:
    models = models.replace(
        "from django.utils.timezone import now\n",
        "from django.utils.timezone import now\nfrom django.utils.text import slugify\n",
    )

models_anchor = """    @property
    def unique_key(self) -> str:
"""
models_insert = """    def next_available_slug(self, desired_slug: str) -> str:
        if not desired_slug:
            return ""

        existing = set(
            Check.objects.filter(project=self.project).values_list("slug", flat=True)
        )

        if desired_slug not in existing:
            return desired_slug

        candidate = f"{desired_slug}-copy"
        n = 2
        while candidate in existing:
            candidate = f"{desired_slug}-copy-{n}"
            n += 1

        return candidate

    def clone_with_overrides(
        self,
        *,
        name: str | None = None,
        slug: str | None = None,
        tags: str | None = None,
    ) -> "Check":
        clone = Check(project=self.project)

        for field in (
            "desc",
            "kind",
            "timeout",
            "grace",
            "schedule",
            "tz",
            "filter_subject",
            "filter_body",
            "start_kw",
            "success_kw",
            "failure_kw",
            "methods",
            "manual_resume",
        ):
            setattr(clone, field, getattr(self, field))

        clone.name = self.name if name is None else name
        clone.tags = self.tags if tags is None else tags

        desired_slug = slug if slug is not None else self.slug
        if not desired_slug and clone.name:
            desired_slug = slugify(clone.name)

        clone.slug = self.next_available_slug(desired_slug) if desired_slug else ""

        clone.status = "new"
        clone.n_pings = 0
        clone.last_ping = None
        clone.last_start = None
        clone.last_start_rid = None
        clone.last_duration = None
        clone.has_confirmation_link = False
        clone.alert_after = None

        clone.save()
        clone.channel_set.set(self.channel_set.all())
        return clone

    @property
    def unique_key(self) -> str:
"""

if "def clone_with_overrides(" not in models:
    if models_anchor not in models:
        raise SystemExit("Could not find insertion point in hc/api/models.py")
    models = models.replace(models_anchor, models_insert)

# --- hc/api/views.py ---
views_anchor = """CUSTOM_ERRORS = {
"""
views_insert = """class CloneSpec(BaseModel):
    name: str | None = Field(None, max_length=100)
    slug: str | None = Field(None, pattern="^[a-z0-9-_]*$")
    tags: str | None = Field(None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def check_nulls(cls, data: dict[str, Any]) -> dict[str, Any]:
        for k, v in data.items():
            if v is None:
                data[k] = float()
        return data


CUSTOM_ERRORS = {
"""

if "class CloneSpec(BaseModel):" not in views:
    if views_anchor not in views:
        raise SystemExit("Could not find CloneSpec insertion point in hc/api/views.py")
    views = views.replace(views_anchor, views_insert)

view_insert_anchor = """@cors("POST")
@csrf_exempt
@authorize
def pause(request: ApiRequest, code: UUID) -> HttpResponse:
"""

clone_view = """@cors("POST")
@csrf_exempt
@authorize
def clone_check(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    try:
        spec = CloneSpec.model_validate(request.json, strict=True)
    except ValidationError as e:
        return JsonResponse({"error": format_first_error(e)}, status=400)

    if request.project.num_checks_available() <= 0:
        return HttpResponseForbidden()

    with transaction.atomic():
        check = get_object_or_404(
            Check.objects.select_for_update().prefetch_related("channel_set"),
            code=code,
        )
        clone = check.clone_with_overrides(
            name=spec.name,
            slug=spec.slug,
            tags=spec.tags,
        )

    return JsonResponse(clone.to_dict(v=request.v), status=201)


@cors("POST")
@csrf_exempt
@authorize
def pause(request: ApiRequest, code: UUID) -> HttpResponse:
"""

if "def clone_check(request: ApiRequest, code: UUID) -> HttpResponse:" not in views:
    if view_insert_anchor not in views:
        raise SystemExit("Could not find clone view insertion point in hc/api/views.py")
    views = views.replace(view_insert_anchor, clone_view)

# --- hc/api/urls.py ---
route_line = '    path("checks/<uuid:code>/clone", views.clone_check, name="hc-api-clone"),\n'
if route_line not in urls:
    marker = '    path("checks/<uuid:code>", views.single, name="hc-api-single"),\n'
    if marker not in urls:
        raise SystemExit("Could not find clone route insertion point in hc/api/urls.py")
    urls = urls.replace(marker, marker + route_line)

models_path.write_text(models)
views_path.write_text(views)
urls_path.write_text(urls)
PY