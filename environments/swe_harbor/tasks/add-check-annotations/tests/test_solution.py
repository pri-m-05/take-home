"""Tests for the Check Annotations feature."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta as td
from datetime import datetime, timezone

from django.test import TestCase
from django.test.utils import override_settings
from django.utils.timezone import now

import os
import sys
sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")
django.setup()

from hc.api.models import Check, Ping
from hc.test import BaseTestCase


class AnnotationModelTestCase(BaseTestCase):
    """Tests for the Annotation model itself."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_annotation_model_exists(self):
        """The Annotation model should be importable."""
        from hc.api.models import Annotation
        self.assertTrue(hasattr(Annotation, 'objects'))

    def test_create_annotation(self):
        """Can create an annotation linked to a check."""
        from hc.api.models import Annotation
        a = Annotation.objects.create(
            owner=self.check,
            summary="Deployed v2.0",
            detail="Released new API version",
            tag="deploy",
        )
        self.assertIsNotNone(a.code)
        self.assertEqual(a.summary, "Deployed v2.0")
        self.assertEqual(a.detail, "Released new API version")
        self.assertEqual(a.tag, "deploy")

    def test_annotation_has_uuid(self):
        """Each annotation should have a unique UUID code."""
        from hc.api.models import Annotation
        a1 = Annotation.objects.create(owner=self.check, summary="First")
        a2 = Annotation.objects.create(owner=self.check, summary="Second")
        self.assertNotEqual(a1.code, a2.code)

    def test_annotation_to_dict(self):
        """to_dict() returns correct keys and values."""
        from hc.api.models import Annotation
        a = Annotation.objects.create(
            owner=self.check,
            summary="Test summary",
            detail="Test detail",
            tag="incident",
        )
        d = a.to_dict()
        self.assertEqual(d["uuid"], str(a.code))
        self.assertEqual(d["summary"], "Test summary")
        self.assertEqual(d["detail"], "Test detail")
        self.assertEqual(d["tag"], "incident")
        self.assertIn("created", d)

    def test_to_dict_created_no_microseconds(self):
        """created in to_dict() should have no microseconds."""
        from hc.api.models import Annotation
        a = Annotation.objects.create(owner=self.check, summary="Test")
        d = a.to_dict()
        # ISO format without microseconds: no '.' in the datetime string
        created_str = d["created"]
        self.assertNotIn(".", created_str,
                         "created should not contain microseconds")

    def test_annotation_default_detail_is_empty(self):
        """detail should default to empty string."""
        from hc.api.models import Annotation
        a = Annotation.objects.create(owner=self.check, summary="Test")
        self.assertEqual(a.detail, "")

    def test_annotation_default_tag_is_empty(self):
        """tag should default to empty string."""
        from hc.api.models import Annotation
        a = Annotation.objects.create(owner=self.check, summary="Test")
        self.assertEqual(a.tag, "")

    def test_annotation_ordering(self):
        """Annotations should be ordered newest first by default."""
        from hc.api.models import Annotation
        a1 = Annotation.objects.create(owner=self.check, summary="First")
        a2 = Annotation.objects.create(owner=self.check, summary="Second")
        annotations = list(Annotation.objects.filter(owner=self.check))
        self.assertEqual(annotations[0].summary, "Second")
        self.assertEqual(annotations[1].summary, "First")

    def test_cascade_delete(self):
        """Deleting a check deletes its annotations."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="Will be deleted")
        self.assertEqual(Annotation.objects.count(), 1)
        self.check.delete()
        self.assertEqual(Annotation.objects.count(), 0)

    def test_related_name(self):
        """check.annotations should work as reverse relation."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="Via relation")
        self.assertEqual(self.check.annotations.count(), 1)


class CreateAnnotationApiTestCase(BaseTestCase):
    """Tests for POST /api/v3/checks/<code>/annotations/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/annotations/"

    def post(self, data, api_key=None):
        if api_key is None:
            api_key = "X" * 32
        return self.client.post(
            self.url,
            json.dumps({**data, "api_key": api_key}),
            content_type="application/json",
        )

    def test_create_annotation(self):
        """POST should create an annotation and return 201."""
        r = self.post({"summary": "Deployed v2.0", "detail": "New version", "tag": "deploy"})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertEqual(doc["summary"], "Deployed v2.0")
        self.assertEqual(doc["detail"], "New version")
        self.assertEqual(doc["tag"], "deploy")
        self.assertIn("uuid", doc)
        self.assertIn("created", doc)

    def test_create_minimal_annotation(self):
        """POST with only summary should work."""
        r = self.post({"summary": "Quick note"})
        self.assertEqual(r.status_code, 201)
        doc = r.json()
        self.assertEqual(doc["summary"], "Quick note")
        self.assertEqual(doc["detail"], "")
        self.assertEqual(doc["tag"], "")

    def test_missing_summary(self):
        """POST without summary should return 400."""
        r = self.post({"detail": "No summary provided"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("summary", r.json()["error"].lower())

    def test_empty_summary(self):
        """POST with empty summary should return 400."""
        r = self.post({"summary": ""})
        self.assertEqual(r.status_code, 400)

    def test_whitespace_only_summary(self):
        """POST with whitespace-only summary should return 400."""
        r = self.post({"summary": "   "})
        self.assertEqual(r.status_code, 400)

    def test_summary_too_long(self):
        """POST with summary > 200 chars should return 400."""
        r = self.post({"summary": "x" * 201})
        self.assertEqual(r.status_code, 400)
        self.assertIn("too long", r.json()["error"].lower())

    def test_tag_too_long(self):
        """POST with tag > 50 chars should return 400."""
        r = self.post({"summary": "Ok", "tag": "x" * 51})
        self.assertEqual(r.status_code, 400)
        self.assertIn("too long", r.json()["error"].lower())

    def test_wrong_api_key(self):
        """POST with wrong API key should return 401."""
        r = self.post({"summary": "Test"}, api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_wrong_project(self):
        """POST for a check in a different project should return 403."""
        other_check = Check.objects.create(project=self.bobs_project, name="Bob's Check")
        url = f"/api/v3/checks/{other_check.code}/annotations/"
        r = self.client.post(
            url,
            json.dumps({"summary": "Hacking", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """POST for a nonexistent check should return 404."""
        fake_uuid = uuid.uuid4()
        url = f"/api/v3/checks/{fake_uuid}/annotations/"
        r = self.client.post(
            url,
            json.dumps({"summary": "Ghost", "api_key": "X" * 32}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_annotation_limit(self):
        """POST should return 403 when check has 100 annotations."""
        from hc.api.models import Annotation
        for i in range(100):
            Annotation.objects.create(owner=self.check, summary=f"Note {i}")

        r = self.post({"summary": "One too many"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("too many", r.json()["error"].lower())

    def test_detail_not_string(self):
        """POST with non-string detail should return 400."""
        r = self.post({"summary": "Ok", "detail": 123})
        self.assertEqual(r.status_code, 400)

    def test_tag_not_string(self):
        """POST with non-string tag should return 400."""
        r = self.post({"summary": "Ok", "tag": 123})
        self.assertEqual(r.status_code, 400)


class ListAnnotationsApiTestCase(BaseTestCase):
    """Tests for GET /api/v3/checks/<code>/annotations/"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")
        self.url = f"/api/v3/checks/{self.check.code}/annotations/"

    def get(self, params="", api_key=None):
        if api_key is None:
            api_key = "X" * 32
        url = self.url
        if params:
            url += "?" + params
        return self.client.get(url, HTTP_X_API_KEY=api_key)

    def test_list_empty(self):
        """GET should return empty list when no annotations exist."""
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["annotations"], [])

    def test_list_annotations(self):
        """GET should return all annotations."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="First")
        Annotation.objects.create(owner=self.check, summary="Second")
        r = self.get()
        self.assertEqual(r.status_code, 200)
        annotations = r.json()["annotations"]
        self.assertEqual(len(annotations), 2)

    def test_list_newest_first(self):
        """GET should return annotations newest first."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="Older")
        Annotation.objects.create(owner=self.check, summary="Newer")
        r = self.get()
        annotations = r.json()["annotations"]
        self.assertEqual(annotations[0]["summary"], "Newer")
        self.assertEqual(annotations[1]["summary"], "Older")

    def test_filter_by_tag(self):
        """GET with ?tag= should filter annotations."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="Deploy", tag="deploy")
        Annotation.objects.create(owner=self.check, summary="Incident", tag="incident")
        r = self.get("tag=deploy")
        annotations = r.json()["annotations"]
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["tag"], "deploy")

    def test_filter_by_start(self):
        """GET with ?start= should filter annotations by start time."""
        from urllib.parse import urlencode
        from hc.api.models import Annotation
        old = Annotation.objects.create(owner=self.check, summary="Old")
        old.created = now() - td(days=10)
        old.save()

        new = Annotation.objects.create(owner=self.check, summary="New")

        start_str = (now() - td(days=1)).isoformat()
        r = self.get(urlencode({"start": start_str}))
        annotations = r.json()["annotations"]
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["summary"], "New")

    def test_filter_by_end(self):
        """GET with ?end= should filter annotations by end time."""
        from urllib.parse import urlencode
        from hc.api.models import Annotation
        old = Annotation.objects.create(owner=self.check, summary="Old")
        old.created = now() - td(days=10)
        old.save()

        Annotation.objects.create(owner=self.check, summary="New")

        end_str = (now() - td(days=1)).isoformat()
        r = self.get(urlencode({"end": end_str}))
        annotations = r.json()["annotations"]
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["summary"], "Old")

    def test_invalid_start_format(self):
        """GET with non-ISO start date should return 400."""
        r = self.get("start=not-a-date")
        self.assertEqual(r.status_code, 400)

    def test_invalid_end_format(self):
        """GET with non-ISO end date should return 400."""
        r = self.get("end=not-a-date")
        self.assertEqual(r.status_code, 400)

    def test_wrong_api_key(self):
        """GET with wrong API key should return 401."""
        r = self.get(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)

    def test_wrong_project(self):
        """GET for a check in a different project should return 403."""
        other_check = Check.objects.create(project=self.bobs_project, name="Bob's Check")
        url = f"/api/v3/checks/{other_check.code}/annotations/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_nonexistent_check(self):
        """GET for a nonexistent check should return 404."""
        fake_uuid = uuid.uuid4()
        url = f"/api/v3/checks/{fake_uuid}/annotations/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_cors_headers(self):
        """Response should include CORS headers."""
        r = self.get()
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")


class CheckToDictAnnotationsTestCase(BaseTestCase):
    """Tests for annotations_count in Check.to_dict()"""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_annotations_count_zero(self):
        """to_dict() should include annotations_count=0 when no annotations."""
        d = self.check.to_dict()
        self.assertIn("annotations_count", d)
        self.assertEqual(d["annotations_count"], 0)

    def test_annotations_count_reflects_actual(self):
        """to_dict() should include correct annotations_count."""
        from hc.api.models import Annotation
        Annotation.objects.create(owner=self.check, summary="A")
        Annotation.objects.create(owner=self.check, summary="B")
        d = self.check.to_dict()
        self.assertEqual(d["annotations_count"], 2)


class AnnotationUrlRoutingTestCase(BaseTestCase):
    """Tests that URL routing works for all API versions."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    def test_v1_endpoint(self):
        """The annotations endpoint should work under /api/v1/."""
        url = f"/api/v1/checks/{self.check.code}/annotations/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v2_endpoint(self):
        """The annotations endpoint should work under /api/v2/."""
        url = f"/api/v2/checks/{self.check.code}/annotations/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_v3_endpoint(self):
        """The annotations endpoint should work under /api/v3/."""
        url = f"/api/v3/checks/{self.check.code}/annotations/"
        r = self.client.get(url, HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 200)

    def test_options_request(self):
        """OPTIONS should return 204 with CORS headers."""
        url = f"/api/v3/checks/{self.check.code}/annotations/"
        r = self.client.options(url)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")


class AnnotationPruneTestCase(BaseTestCase):
    """Tests for annotation cleanup in Check.prune()."""

    def setUp(self):
        super().setUp()
        self.check = Check.objects.create(project=self.project, name="Test Check")

    @override_settings(S3_BUCKET=None)
    def test_prune_deletes_old_annotations(self):
        """prune() should delete annotations older than the oldest retained ping."""
        from hc.api.models import Annotation

        # Create a ping so prune has a reference point
        self.check.n_pings = 1
        self.check.save()
        ping_time = now()
        Ping.objects.create(owner=self.check, n=1, created=ping_time)

        # Create annotations: one before the ping, one after
        old_annotation = Annotation.objects.create(
            owner=self.check, summary="Old note"
        )
        old_annotation.created = ping_time - td(days=1)
        old_annotation.save()

        new_annotation = Annotation.objects.create(
            owner=self.check, summary="New note"
        )
        new_annotation.created = ping_time + td(hours=1)
        new_annotation.save()

        self.check.prune()

        # Old annotation should be deleted, new one retained
        remaining = list(Annotation.objects.filter(owner=self.check))
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].summary, "New note")
