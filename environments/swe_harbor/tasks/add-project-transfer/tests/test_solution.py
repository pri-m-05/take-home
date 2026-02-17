"""Tests for the Check Transfer API feature."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta as td

from django.test import TestCase
from django.utils.timezone import now

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Channel, Check, Flip, Ping
from hc.accounts.models import Project
from hc.test import BaseTestCase


class TransferLogModelTestCase(BaseTestCase):
    """Tests for the TransferLog model."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_model_exists(self):
        """TransferLog model should be importable."""
        from hc.api.models import TransferLog
        self.assertTrue(hasattr(TransferLog, 'objects'))

    def test_create_transfer_log(self):
        """Can create a TransferLog entry."""
        from hc.api.models import TransferLog
        log = TransferLog.objects.create(
            owner=self.check,
            from_project=self.project,
            to_project=self.bobs_project,
            transferred_by="alice@example.org",
        )
        self.assertIsNotNone(log.code)
        self.assertEqual(log.transferred_by, "alice@example.org")

    def test_to_dict(self):
        """to_dict() returns correct keys and values."""
        from hc.api.models import TransferLog
        log = TransferLog.objects.create(
            owner=self.check,
            from_project=self.project,
            to_project=self.bobs_project,
            transferred_by="alice@example.org",
        )
        d = log.to_dict()
        self.assertEqual(d["uuid"], str(log.code))
        self.assertEqual(d["check"], str(self.check.code))
        self.assertEqual(d["from_project"], str(self.project.code))
        self.assertEqual(d["to_project"], str(self.bobs_project.code))
        self.assertEqual(d["transferred_by"], "alice@example.org")
        self.assertIn("created", d)

    def test_to_dict_null_projects(self):
        """to_dict() handles null project references gracefully."""
        from hc.api.models import TransferLog
        log = TransferLog.objects.create(
            owner=self.check,
            from_project=None,
            to_project=None,
        )
        d = log.to_dict()
        self.assertIsNone(d["from_project"])
        self.assertIsNone(d["to_project"])

    def test_ordering(self):
        """TransferLog entries should be ordered newest first."""
        from hc.api.models import TransferLog
        t1 = TransferLog.objects.create(
            owner=self.check, from_project=self.project, to_project=self.bobs_project
        )
        t2 = TransferLog.objects.create(
            owner=self.check, from_project=self.bobs_project, to_project=self.project
        )
        logs = list(TransferLog.objects.filter(owner=self.check))
        self.assertEqual(logs[0].id, t2.id)

    def test_cascade_delete(self):
        """Deleting a check deletes its transfer logs."""
        from hc.api.models import TransferLog
        TransferLog.objects.create(
            owner=self.check, from_project=self.project, to_project=self.bobs_project
        )
        self.check.delete()
        from hc.api.models import TransferLog
        self.assertEqual(TransferLog.objects.count(), 0)


class CheckTransferMethodTestCase(BaseTestCase):
    """Tests for the Check.transfer() method."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(
            project=self.project,
            name="Transfer Me",
            status="up",
            n_pings=5,
        )
        self.check.last_ping = now()
        self.check.save()

        # Create some pings and flips
        Ping.objects.create(owner=self.check, n=1, created=now())
        Ping.objects.create(owner=self.check, n=2, created=now())
        Flip.objects.create(
            owner=self.check, created=now(), old_status="new", new_status="up"
        )

        # Create a channel in the target project
        self.target_channel = Channel.objects.create(
            project=self.bobs_project, kind="email", value="bob@example.org"
        )

    def test_transfer_moves_check(self):
        """transfer() should move the check to the target project."""
        self.check.transfer(self.bobs_project)
        self.check.refresh_from_db()
        self.assertEqual(self.check.project_id, self.bobs_project.id)

    def test_transfer_resets_status(self):
        """transfer() should reset check status to 'new'."""
        self.check.transfer(self.bobs_project)
        self.check.refresh_from_db()
        self.assertEqual(self.check.status, "new")

    def test_transfer_clears_pings(self):
        """transfer() should delete all pings."""
        self.check.transfer(self.bobs_project)
        self.assertEqual(Ping.objects.filter(owner=self.check).count(), 0)

    def test_transfer_clears_flips(self):
        """transfer() should delete all flips."""
        self.check.transfer(self.bobs_project)
        self.assertEqual(Flip.objects.filter(owner=self.check).count(), 0)

    def test_transfer_resets_n_pings(self):
        """transfer() should reset n_pings to 0."""
        self.check.transfer(self.bobs_project)
        self.check.refresh_from_db()
        self.assertEqual(self.check.n_pings, 0)

    def test_transfer_clears_last_ping(self):
        """transfer() should clear last_ping."""
        self.check.transfer(self.bobs_project)
        self.check.refresh_from_db()
        self.assertIsNone(self.check.last_ping)

    def test_transfer_clears_alert_after(self):
        """transfer() should clear alert_after."""
        self.check.alert_after = now() + td(hours=1)
        self.check.save()
        self.check.transfer(self.bobs_project)
        self.check.refresh_from_db()
        self.assertIsNone(self.check.alert_after)

    def test_transfer_reassigns_channels(self):
        """transfer() should reassign channels from target project."""
        source_channel = Channel.objects.create(
            project=self.project, kind="email", value="alice@example.org"
        )
        self.check.channel_set.add(source_channel)
        self.check.transfer(self.bobs_project)

        assigned = list(self.check.channel_set.all())
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned[0].id, self.target_channel.id)

    def test_transfer_creates_log(self):
        """transfer() should create a TransferLog entry."""
        from hc.api.models import TransferLog
        self.check.transfer(self.bobs_project, transferred_by="alice@example.org")
        logs = TransferLog.objects.filter(owner=self.check)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.from_project_id, self.project.id)
        self.assertEqual(log.to_project_id, self.bobs_project.id)
        self.assertEqual(log.transferred_by, "alice@example.org")

    def test_transfer_raises_on_no_capacity(self):
        """transfer() should raise ValueError if target has no capacity."""
        from hc.accounts.models import Profile
        profile = Profile.objects.for_user(self.bob)
        profile.check_limit = 1
        profile.save()
        # Fill the one available slot
        Check.objects.create(project=self.bobs_project, name="Filler")

        with self.assertRaises(ValueError) as ctx:
            self.check.transfer(self.bobs_project)
        self.assertIn("no checks available", str(ctx.exception))


class TransferApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/transfer/"""

    def setUp(self):
        super().setUp()
        # Give Bob's project its own unique API key
        self.bobs_project.api_key = "B" * 32
        self.bobs_project.save()

        self.check = Check.objects.create(project=self.project, name="Transfer Me")
        self.url = f"/api/v3/checks/{self.check.code}/transfer/"

    def post(self, data, api_key=None, target_api_key=None):
        if api_key is None:
            api_key = "X" * 32
        payload = {**data, "api_key": api_key}
        if target_api_key is not None:
            payload["target_api_key"] = target_api_key
        elif "target_api_key" not in data:
            payload["target_api_key"] = "B" * 32
        return self.client.post(
            self.url,
            json.dumps(payload),
            content_type="application/json",
        )

    def test_transfer_succeeds(self):
        """POST should transfer the check and return 200."""
        r = self.post({"project": str(self.bobs_project.code)})
        self.assertEqual(r.status_code, 200)
        self.check.refresh_from_db()
        self.assertEqual(self.check.project_id, self.bobs_project.id)

    def test_transfer_returns_check_dict(self):
        """POST should return the check's to_dict() representation."""
        r = self.post({"project": str(self.bobs_project.code)})
        doc = r.json()
        self.assertIn("name", doc)
        self.assertEqual(doc["name"], "Transfer Me")
        self.assertEqual(doc["status"], "new")

    def test_missing_project_field(self):
        """POST without project should return 400."""
        r = self.post({})
        self.assertEqual(r.status_code, 400)
        self.assertIn("missing project", r.json()["error"])

    def test_invalid_project_uuid(self):
        """POST with invalid UUID should return 400."""
        r = self.post({"project": "not-a-uuid"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid project uuid", r.json()["error"])

    def test_nonexistent_target_project(self):
        """POST with nonexistent project UUID should return 404."""
        r = self.post({"project": str(uuid.uuid4())})
        self.assertEqual(r.status_code, 404)

    def test_same_project(self):
        """POST transferring to same project should return 400."""
        r = self.post({"project": str(self.project.code)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("same project", r.json()["error"])

    def test_unauthorized_target_project(self):
        """POST should return 403 if target_api_key doesn't match target project."""
        r = self.post(
            {"project": str(self.bobs_project.code)},
            target_api_key="Z" * 32,
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("not authorized", r.json()["error"])

    def test_wrong_api_key(self):
        """POST with wrong API key should return 401."""
        r = self.post({"project": str(self.bobs_project.code)}, api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_wrong_source_project(self):
        """POST for check in different project should return 403."""
        other_check = Check.objects.create(project=self.charlies_project, name="Other")
        url = f"/api/v3/checks/{other_check.code}/transfer/"
        r = self.client.post(
            url,
            json.dumps({
                "project": str(self.bobs_project.code),
                "api_key": "X" * 32,
                "target_api_key": "B" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """POST for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/transfer/"
        r = self.client.post(
            url,
            json.dumps({
                "project": str(self.bobs_project.code),
                "api_key": "X" * 32,
                "target_api_key": "B" * 32,
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)


class TransfersHistoryApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/transfers/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/transfers/"

    def test_list_empty(self):
        """GET should return empty list when no transfers."""
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["transfers"], [])

    def test_list_transfers(self):
        """GET should return transfer log entries."""
        from hc.api.models import TransferLog
        TransferLog.objects.create(
            owner=self.check,
            from_project=self.project,
            to_project=self.bobs_project,
            transferred_by="alice@example.org",
        )
        r = self.client.get(self.url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)
        transfers = r.json()["transfers"]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0]["transferred_by"], "alice@example.org")

    def test_wrong_project(self):
        """GET for check in different project should return 403."""
        other_check = Check.objects.create(project=self.bobs_project, name="Other")
        url = f"/api/v3/checks/{other_check.code}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """GET for nonexistent check should return 404."""
        url = f"/api/v3/checks/{uuid.uuid4()}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_wrong_api_key(self):
        """GET with wrong API key should return 401."""
        r = self.client.get(self.url, HTTP_X_API_KEY="Y" * 32)
        self.assertEqual(r.status_code, 401)


class CheckToDictTransfersTestCase(BaseTestCase):
    """Tests for transfers_count in Check.to_dict()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_transfers_count_zero(self):
        """to_dict() should include transfers_count=0 initially."""
        d = self.check.to_dict()
        self.assertIn("transfers_count", d)
        self.assertEqual(d["transfers_count"], 0)

    def test_transfers_count_reflects_actual(self):
        """to_dict() should include correct transfers_count."""
        from hc.api.models import TransferLog
        TransferLog.objects.create(
            owner=self.check, from_project=self.project, to_project=self.bobs_project
        )
        TransferLog.objects.create(
            owner=self.check, from_project=self.bobs_project, to_project=self.project
        )
        d = self.check.to_dict()
        self.assertEqual(d["transfers_count"], 2)


class UrlRoutingTestCase(BaseTestCase):
    """Tests for URL routing across API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_v1_transfers_endpoint(self):
        """Transfer history should work under /api/v1/."""
        url = f"/api/v1/checks/{self.check.code}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v2_transfers_endpoint(self):
        """Transfer history should work under /api/v2/."""
        url = f"/api/v2/checks/{self.check.code}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v3_transfers_endpoint(self):
        """Transfer history should work under /api/v3/."""
        url = f"/api/v3/checks/{self.check.code}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_transfer_cors(self):
        """Transfer endpoint should return CORS headers."""
        url = f"/api/v3/checks/{self.check.code}/transfers/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
