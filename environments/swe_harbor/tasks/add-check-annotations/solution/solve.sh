#!/bin/bash
set -e

###############################################################################
# 1. Add the Annotation model to hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class Annotation(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="annotations")
    created = models.DateTimeField(default=now)
    summary = models.CharField(max_length=200)
    detail = models.TextField(blank=True, default="")
    tag = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["-created"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "created": isostring(self.created),
            "summary": self.summary,
            "detail": self.detail,
            "tag": self.tag,
        }
PYEOF

###############################################################################
# 2. Update Check.to_dict() — add annotations_count
###############################################################################

cd /app

python3 << 'PATCH1'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

new = '''        result["annotations_count"] = self.annotations.count()

        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Update Check.prune() — prune old annotations
###############################################################################

python3 << 'PATCH2'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''            # Delete flips older than the oldest retained ping *and*
            # older than 93 days. We need ~3 months of flips for calculating
            # downtime statistics. The precise requirement is
            # "we need the current month and full two previous months of data".
            # We could calculate this precisely, but 3*31 is close enough and
            # much simpler.
            flip_threshold = min(ping.created, now() - td(days=93))
            self.flip_set.filter(created__lt=flip_threshold).delete()'''

new = '''            # Delete flips older than the oldest retained ping *and*
            # older than 93 days. We need ~3 months of flips for calculating
            # downtime statistics. The precise requirement is
            # "we need the current month and full two previous months of data".
            # We could calculate this precisely, but 3*31 is close enough and
            # much simpler.
            flip_threshold = min(ping.created, now() - td(days=93))
            self.flip_set.filter(created__lt=flip_threshold).delete()

            # Delete annotations older than the oldest retained ping
            self.annotations.filter(created__lt=ping.created).delete()'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 4. Add API views for annotations
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@authorize_read
def list_annotations(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import Annotation

    q = Annotation.objects.filter(owner=check)

    if tag := request.GET.get("tag"):
        q = q.filter(tag=tag)

    if start := request.GET.get("start"):
        try:
            start_dt = datetime.fromisoformat(start)
            q = q.filter(created__gte=start_dt)
        except ValueError:
            return HttpResponseBadRequest()

    if end := request.GET.get("end"):
        try:
            end_dt = datetime.fromisoformat(end)
            q = q.filter(created__lt=end_dt)
        except ValueError:
            return HttpResponseBadRequest()

    return JsonResponse({"annotations": [a.to_dict() for a in q]})


@authorize
def create_annotation(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import Annotation

    if check.annotations.count() >= 100:
        return JsonResponse({"error": "too many annotations"}, status=403)

    summary = request.json.get("summary", "")
    if not isinstance(summary, str) or not summary.strip():
        return JsonResponse({"error": "summary is required"}, status=400)

    if len(summary) > 200:
        return JsonResponse({"error": "summary is too long"}, status=400)

    detail = request.json.get("detail", "")
    if not isinstance(detail, str):
        return JsonResponse({"error": "detail is not a string"}, status=400)

    tag = request.json.get("tag", "")
    if not isinstance(tag, str):
        return JsonResponse({"error": "tag is not a string"}, status=400)

    if len(tag) > 50:
        return JsonResponse({"error": "tag is too long"}, status=400)

    annotation = Annotation(
        owner=check,
        summary=summary.strip(),
        detail=detail,
        tag=tag,
    )
    annotation.save()

    return JsonResponse(annotation.to_dict(), status=201)


@csrf_exempt
@cors("GET", "POST")
def check_annotations(request: HttpRequest, code: UUID) -> HttpResponse:
    if request.method == "POST":
        return create_annotation(request, code)

    return list_annotations(request, code)
VIEWEOF

###############################################################################
# 5. Add URL routes
###############################################################################

python3 << 'PATCH3'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '''    path("channels/", views.channels),'''

new = '''    path(
        "checks/<uuid:code>/annotations/",
        views.check_annotations,
        name="hc-api-annotations",
    ),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 6. Create the migration
###############################################################################

cd /app
python manage.py makemigrations api --name annotation 2>&1
python manage.py migrate 2>&1
