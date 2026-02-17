#!/bin/bash
set -e
cd /app

###############################################################################
# 1. Add TransferLog model and Check.transfer() to hc/api/models.py
###############################################################################

cat >> /app/hc/api/models.py << 'PYEOF'


class TransferLog(models.Model):
    code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner = models.ForeignKey(Check, models.CASCADE, related_name="transfers")
    from_project = models.ForeignKey(
        "accounts.Project", models.SET_NULL, null=True, related_name="+"
    )
    to_project = models.ForeignKey(
        "accounts.Project", models.SET_NULL, null=True, related_name="+"
    )
    created = models.DateTimeField(default=now)
    transferred_by = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created"]

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.code),
            "check": str(self.owner.code),
            "from_project": str(self.from_project.code) if self.from_project else None,
            "to_project": str(self.to_project.code) if self.to_project else None,
            "created": isostring(self.created),
            "transferred_by": self.transferred_by,
        }
PYEOF

###############################################################################
# 2. Add Check.transfer() method
###############################################################################

python3 << 'PATCH1'
with open("hc/api/models.py", "r") as f:
    content = f.read()

# Insert transfer method after the assign_all_channels method
old = '''    def assign_all_channels(self) -> None:
        channels = Channel.objects.filter(project=self.project)
        self.channel_set.set(channels)'''

new = '''    def assign_all_channels(self) -> None:
        channels = Channel.objects.filter(project=self.project)
        self.channel_set.set(channels)

    def transfer(self, target_project, transferred_by=""):
        """Transfer this check to another project.

        Moves the check, reassigns channels, resets alert state, and cleans up
        old data. The entire operation is atomic.
        """
        if target_project.num_checks_available() <= 0:
            raise ValueError("target project has no checks available")

        with transaction.atomic():
            check = Check.objects.select_for_update().get(id=self.id)

            TransferLog.objects.create(
                owner=check,
                from_project=check.project,
                to_project=target_project,
                transferred_by=transferred_by,
            )

            check.project = target_project
            check.channel_set.clear()
            check.channel_set.set(Channel.objects.filter(project=target_project))

            check.status = "new"
            check.last_start = None
            check.last_ping = None
            check.alert_after = None
            check.last_duration = None
            check.n_pings = 0
            check.save()

            Ping.objects.filter(owner=check).delete()
            Flip.objects.filter(owner=check).delete()

            # Update self to reflect DB state
            self.project = check.project
            self.status = check.status
            self.last_start = check.last_start
            self.last_ping = check.last_ping
            self.alert_after = check.alert_after
            self.last_duration = check.last_duration
            self.n_pings = check.n_pings'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH1

###############################################################################
# 3. Add transfers_count to Check.to_dict()
###############################################################################

python3 << 'PATCH2'
with open("hc/api/models.py", "r") as f:
    content = f.read()

old = '''        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

new = '''        result["transfers_count"] = self.transfers.count()

        if self.kind == "simple":
            result["timeout"] = int(self.timeout.total_seconds())
        elif self.kind in ("cron", "oncalendar"):
            result["schedule"] = self.schedule
            result["tz"] = self.tz

        return result'''

content = content.replace(old, new, 1)

with open("hc/api/models.py", "w") as f:
    f.write(content)
PATCH2

###############################################################################
# 4. Add API views for transfer
###############################################################################

cat >> /app/hc/api/views.py << 'VIEWEOF'


@cors("POST")
@csrf_exempt
@authorize
def check_transfer(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    target_project_str = request.json.get("project", "")
    if not target_project_str:
        return JsonResponse({"error": "missing project"}, status=400)

    from hc.lib.string import is_valid_uuid_string
    if not is_valid_uuid_string(str(target_project_str)):
        return JsonResponse({"error": "invalid project uuid"}, status=400)

    target_uuid = UUID(str(target_project_str))

    try:
        target_project = Project.objects.get(code=target_uuid)
    except Project.DoesNotExist:
        return HttpResponseNotFound()

    if target_project.id == check.project_id:
        return JsonResponse({"error": "cannot transfer to same project"}, status=400)

    # Verify write access to target project via target_api_key
    target_api_key = str(request.json.get("target_api_key", ""))
    if not target_api_key or target_project.api_key != target_api_key:
        return JsonResponse({"error": "not authorized for target project"}, status=403)

    try:
        transferred_by = request.project.owner.email
        check.transfer(target_project, transferred_by=transferred_by)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse(check.to_dict(v=request.v))


@cors("GET")
@csrf_exempt
@authorize_read
def check_transfers(request: ApiRequest, code: UUID) -> HttpResponse:
    check = get_object_or_404(Check, code=code)
    if check.project_id != request.project.id:
        return HttpResponseForbidden()

    from hc.api.models import TransferLog
    logs = TransferLog.objects.filter(owner=check)
    return JsonResponse({"transfers": [t.to_dict() for t in logs]})
VIEWEOF

###############################################################################
# 5. Add URL routes
###############################################################################

python3 << 'PATCH3'
with open("hc/api/urls.py", "r") as f:
    content = f.read()

old = '    path("channels/", views.channels),'

new = '''    path(
        "checks/<uuid:code>/transfer/",
        views.check_transfer,
        name="hc-api-transfer",
    ),
    path(
        "checks/<uuid:code>/transfers/",
        views.check_transfers,
        name="hc-api-transfers",
    ),
    path("channels/", views.channels),'''

content = content.replace(old, new, 1)

with open("hc/api/urls.py", "w") as f:
    f.write(content)
PATCH3

###############################################################################
# 6. Create migration and apply
###############################################################################

python manage.py makemigrations api --name transferlog 2>&1
python manage.py migrate 2>&1
