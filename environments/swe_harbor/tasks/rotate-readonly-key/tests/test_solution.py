import json

from hc.accounts.models import Project
from hc.api.models import Check
from hc.test import BaseTestCase

ROTATE_URL = "/api/v3/project/rotate_readonly_key/"
CHECKS_URL = "/api/v3/checks/"


class TestRotateReadonlyKey(BaseTestCase):
    def rotate(self, api_key=None, body=None):
        payload = {} if body is None else dict(body)
        if api_key is not None:
            payload["api_key"] = api_key

        return self.client.post(
            ROTATE_URL,
            json.dumps(payload),
            content_type="application/json",
        )

    def get_checks(self, api_key):
        return self.client.get(CHECKS_URL, HTTP_X_API_KEY=api_key)

    def test_missing_api_key_returns_401(self):
        r = self.client.post(
            ROTATE_URL,
            json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "missing api key")

    def test_wrong_api_key_returns_401(self):
        r = self.rotate(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "wrong api key")

    def test_readonly_key_cannot_rotate(self):
        self.project.api_key_readonly = "R" * 32
        self.project.save(update_fields=["api_key_readonly"])

        r = self.rotate(api_key="R" * 32)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "wrong api key")

    def test_invalid_json_returns_400(self):
        r = self.client.post(
            ROTATE_URL,
            "{not json",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "could not parse request body")

    def test_get_returns_405(self):
        r = self.client.get(ROTATE_URL)
        self.assertEqual(r.status_code, 405)

    def test_success_rotates_key_and_updates_project(self):
        self.project.api_key_readonly = ""
        self.project.save(update_fields=["api_key_readonly"])

        r = self.rotate(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)

        doc = r.json()
        self.assertIn("api_key_readonly", doc)

        new_key = doc["api_key_readonly"]
        self.assertIsInstance(new_key, str)
        self.assertEqual(len(new_key), 32)
        self.assertEqual(new_key.strip(), new_key)
        self.assertNotEqual(new_key, "X" * 32)

        refreshed = Project.objects.get(id=self.project.id)
        self.assertEqual(refreshed.api_key_readonly, new_key)

    def test_second_rotation_replaces_old_key(self):
        self.project.api_key_readonly = "R" * 32
        self.project.save(update_fields=["api_key_readonly"])

        r1 = self.rotate(api_key="X" * 32)
        self.assertEqual(r1.status_code, 200)
        k1 = r1.json()["api_key_readonly"]

        r2 = self.rotate(api_key="X" * 32)
        self.assertEqual(r2.status_code, 200)
        k2 = r2.json()["api_key_readonly"]

        self.assertNotEqual(k1, k2)

        old_key_response = self.get_checks(k1)
        self.assertEqual(old_key_response.status_code, 401)
        self.assertEqual(old_key_response.json()["error"], "wrong api key")

    def test_new_readonly_key_can_list_checks(self):
        Check.objects.create(project=self.project, name="c1")

        r = self.rotate(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)
        readonly_key = r.json()["api_key_readonly"]

        r2 = self.get_checks(readonly_key)
        self.assertEqual(r2.status_code, 200)

        payload = r2.json()
        self.assertIn("checks", payload)
        self.assertEqual(len(payload["checks"]), 1)

        check = payload["checks"][0]
        self.assertIn("unique_key", check)
        self.assertNotIn("uuid", check)

    def test_rotation_is_scoped_to_authenticated_project(self):
        self.project.api_key_readonly = "A" * 32
        self.project.save(update_fields=["api_key_readonly"])

        self.bobs_project.api_key = "B" * 32
        self.bobs_project.api_key_readonly = "C" * 32
        self.bobs_project.save()

        r = self.rotate(api_key="B" * 32)
        self.assertEqual(r.status_code, 200)
        bob_new_key = r.json()["api_key_readonly"]

        alice = Project.objects.get(id=self.project.id)
        bob = Project.objects.get(id=self.bobs_project.id)

        self.assertEqual(alice.api_key_readonly, "A" * 32)
        self.assertEqual(bob.api_key_readonly, bob_new_key)
        self.assertNotEqual(bob_new_key, "C" * 32)
