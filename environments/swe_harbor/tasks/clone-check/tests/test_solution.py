import json
from datetime import timedelta as td
from uuid import uuid4

from django.utils.timezone import now

from hc.api.models import Channel, Check
from hc.test import BaseTestCase

def clone_url(code):
    return f"/api/v3/checks/{code}/clone"


class TestCloneCheck(BaseTestCase):
    def make_source(self, **overrides):
        data = {
            "project": self.project,
            "name": "Alpha Job",
            "slug": "alpha",
            "tags": "prod db",
            "desc": "important job",
            "kind": "simple",
            "timeout": td(minutes=10),
            "grace": td(minutes=5),
            "filter_subject": True,
            "filter_body": True,
            "start_kw": "START",
            "success_kw": "OK",
            "failure_kw": "FAIL",
            "methods": "POST",
            "manual_resume": True,
            "status": "down",
            "n_pings": 7,
            "last_ping": now(),
            "last_start": now(),
            "last_duration": td(seconds=30),
            "has_confirmation_link": True,
            "alert_after": now(),
        }
        data.update(overrides)
        return Check.objects.create(**data)

    def post(self, code, api_key=None, body=None):
        payload = {} if body is None else dict(body)
        headers = {}
        if api_key is not None:
            headers["HTTP_X_API_KEY"] = api_key

        return self.client.post(
            clone_url(code),
            json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_missing_api_key_returns_401(self):
        source = self.make_source()
        r = self.post(source.code)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "missing api key")

    def test_wrong_api_key_returns_401(self):
        source = self.make_source()
        r = self.post(source.code, api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "wrong api key")

    def test_get_returns_405(self):
        source = self.make_source()
        r = self.client.get(clone_url(source.code), HTTP_X_API_KEY="X" * 32)
        self.assertEqual(r.status_code, 405)

    def test_options_returns_204(self):
        source = self.make_source()
        r = self.client.options(clone_url(source.code))
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", r["Access-Control-Allow-Methods"])

    def test_nonexistent_check_returns_404(self):
        r = self.post(uuid4(), api_key="X" * 32)
        self.assertEqual(r.status_code, 404)

    def test_other_projects_check_returns_403(self):
        source = Check.objects.create(project=self.project, name="Alpha", slug="alpha")

        self.bobs_project.api_key = "B" * 32
        self.bobs_project.save(update_fields=["api_key"])

        r = self.post(source.code, api_key="B" * 32)
        self.assertEqual(r.status_code, 403)

    def test_check_limit_returns_403(self):
        source = self.make_source()

        self.profile.check_limit = 1
        self.profile.save(update_fields=["check_limit"])

        r = self.post(source.code, api_key="X" * 32)
        self.assertEqual(r.status_code, 403)

    def test_invalid_payload_returns_400(self):
        source = self.make_source()
        r = self.post(source.code, api_key="X" * 32, body={"name": 123})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "json validation error: name is not a string")

    def test_success_clones_fields_resets_runtime_and_copies_channels(self):
        source = self.make_source()

        ch1 = Channel.objects.create(
            project=self.project,
            kind="email",
            value="a@example.com",
            name="A",
        )
        ch2 = Channel.objects.create(
            project=self.project,
            kind="email",
            value="b@example.com",
            name="B",
        )
        source.channel_set.set([ch1, ch2])

        r = self.post(source.code, api_key="X" * 32)
        self.assertEqual(r.status_code, 201)

        doc = r.json()
        self.assertIn("uuid", doc)
        self.assertNotEqual(doc["uuid"], str(source.code))

        clone = Check.objects.get(code=doc["uuid"])

        # copied fields
        self.assertEqual(clone.project_id, source.project_id)
        self.assertEqual(clone.name, source.name)
        self.assertEqual(clone.tags, source.tags)
        self.assertEqual(clone.desc, source.desc)
        self.assertEqual(clone.kind, source.kind)
        self.assertEqual(clone.timeout, source.timeout)
        self.assertEqual(clone.grace, source.grace)
        self.assertEqual(clone.filter_subject, source.filter_subject)
        self.assertEqual(clone.filter_body, source.filter_body)
        self.assertEqual(clone.start_kw, source.start_kw)
        self.assertEqual(clone.success_kw, source.success_kw)
        self.assertEqual(clone.failure_kw, source.failure_kw)
        self.assertEqual(clone.methods, source.methods)
        self.assertEqual(clone.manual_resume, source.manual_resume)

        # reset runtime fields
        self.assertEqual(clone.status, "new")
        self.assertEqual(clone.n_pings, 0)
        self.assertIsNone(clone.last_ping)
        self.assertIsNone(clone.last_start)
        self.assertIsNone(clone.last_start_rid)
        self.assertIsNone(clone.last_duration)
        self.assertFalse(clone.has_confirmation_link)
        self.assertIsNone(clone.alert_after)

        # copied channels
        self.assertEqual(clone.channel_set.count(), 2)
        self.assertEqual(
            set(clone.channel_set.values_list("code", flat=True)),
            set(source.channel_set.values_list("code", flat=True)),
        )

        # slug collision behavior
        self.assertEqual(clone.slug, "alpha-copy")

    def test_slug_collision_appends_copy_suffixes(self):
        source = self.make_source(slug="alpha")

        r1 = self.post(source.code, api_key="X" * 32)
        self.assertEqual(r1.status_code, 201)
        c1 = Check.objects.get(code=r1.json()["uuid"])
        self.assertEqual(c1.slug, "alpha-copy")

        r2 = self.post(source.code, api_key="X" * 32)
        self.assertEqual(r2.status_code, 201)
        c2 = Check.objects.get(code=r2.json()["uuid"])
        self.assertEqual(c2.slug, "alpha-copy-2")

    def test_overrides_name_slug_and_tags(self):
        source = self.make_source(name="Alpha Job", slug="alpha", tags="prod db")

        r = self.post(
            source.code,
            api_key="X" * 32,
            body={
                "name": "Cloned Job",
                "slug": "manual-slug",
                "tags": "nightly qa",
            },
        )
        self.assertEqual(r.status_code, 201)

        clone = Check.objects.get(code=r.json()["uuid"])
        self.assertEqual(clone.name, "Cloned Job")
        self.assertEqual(clone.slug, "manual-slug")
        self.assertEqual(clone.tags, "nightly qa")