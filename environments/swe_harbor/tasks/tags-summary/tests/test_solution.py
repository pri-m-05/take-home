import json

from hc.api.models import Check
from hc.test import BaseTestCase

TAGS_URL = "/api/v3/tags/"


class TestTagsSummary(BaseTestCase):
    def get(self, api_key=None, query=""):
        headers = {}
        if api_key is not None:
            headers["HTTP_X_API_KEY"] = api_key
        return self.client.get(f"{TAGS_URL}{query}", **headers)

    def post(self, api_key=None):
        headers = {}
        if api_key is not None:
            headers["HTTP_X_API_KEY"] = api_key
        return self.client.post(
            TAGS_URL,
            json.dumps({}),
            content_type="application/json",
            **headers,
        )

    def test_missing_api_key_returns_401(self):
        r = self.get()
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "missing api key")

    def test_wrong_api_key_returns_401(self):
        r = self.get(api_key="Y" * 32)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "wrong api key")

    def test_options_returns_204(self):
        r = self.client.options(TAGS_URL)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
        self.assertIn("GET", r["Access-Control-Allow-Methods"])

    def test_post_returns_405(self):
        r = self.post(api_key="X" * 32)
        self.assertEqual(r.status_code, 405)

    def test_empty_project_returns_empty_list(self):
        r = self.get(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"tags": []})

    def test_it_counts_tags_for_authenticated_project_only(self):
        Check.objects.create(project=self.project, name="c1", tags="prod db prod")
        Check.objects.create(project=self.project, name="c2", tags="prod nightly")
        Check.objects.create(project=self.project, name="c3", tags="db")
        Check.objects.create(project=self.bobs_project, name="bob1", tags="prod")

        r = self.get(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)

        doc = r.json()
        self.assertIn("tags", doc)

        self.assertEqual(
            doc["tags"],
            [
                {"tag": "db", "n_checks": 2},
                {"tag": "nightly", "n_checks": 1},
                {"tag": "prod", "n_checks": 2},
            ],
        )

    def test_duplicate_tags_in_one_check_count_once(self):
        Check.objects.create(project=self.project, name="c1", tags="prod prod prod")
        r = self.get(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tags"], [{"tag": "prod", "n_checks": 1}])

    def test_blank_tags_are_ignored(self):
        Check.objects.create(project=self.project, name="c1", tags="   ")
        Check.objects.create(project=self.project, name="c2", tags="  db   prod  ")
        r = self.get(api_key="X" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()["tags"],
            [
                {"tag": "db", "n_checks": 1},
                {"tag": "prod", "n_checks": 1},
            ],
        )

    def test_readonly_key_works(self):
        self.project.api_key_readonly = "R" * 32
        self.project.save(update_fields=["api_key_readonly"])

        Check.objects.create(project=self.project, name="c1", tags="prod")
        r = self.get(api_key="R" * 32)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tags"], [{"tag": "prod", "n_checks": 1}])

    def test_q_filters_case_insensitive_prefix(self):
        Check.objects.create(project=self.project, name="c1", tags="prod preprod db")
        Check.objects.create(project=self.project, name="c2", tags="private")
        Check.objects.create(project=self.project, name="c3", tags="nightly")

        r = self.get(api_key="X" * 32, query="?q=PR")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()["tags"],
            [
                {"tag": "preprod", "n_checks": 1},
                {"tag": "private", "n_checks": 1},
                {"tag": "prod", "n_checks": 1},
            ],
        )

    def test_min_checks_filters_results(self):
        Check.objects.create(project=self.project, name="c1", tags="prod db")
        Check.objects.create(project=self.project, name="c2", tags="prod nightly")

        r = self.get(api_key="X" * 32, query="?min_checks=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tags"], [{"tag": "prod", "n_checks": 2}])

    def test_q_and_min_checks_work_together(self):
        Check.objects.create(project=self.project, name="c1", tags="prod preprod")
        Check.objects.create(project=self.project, name="c2", tags="prod")
        Check.objects.create(project=self.project, name="c3", tags="private")

        r = self.get(api_key="X" * 32, query="?q=pr&min_checks=2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tags"], [{"tag": "prod", "n_checks": 2}])

    def test_invalid_min_checks_returns_400(self):
        r = self.get(api_key="X" * 32, query="?min_checks=abc")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json()["error"],
            "min_checks must be a non-negative integer",
        )

    def test_negative_min_checks_returns_400(self):
        r = self.get(api_key="X" * 32, query="?min_checks=-1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.json()["error"],
            "min_checks must be a non-negative integer",
        )
