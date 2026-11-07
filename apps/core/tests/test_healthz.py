from django.test import SimpleTestCase


class HealthzTests(SimpleTestCase):
    def test_get_healthz(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_post_healthz_is_not_allowed(self):
        response = self.client.post("/healthz/")
        self.assertEqual(response.status_code, 405)
