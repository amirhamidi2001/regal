from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class _StylesheetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "link" and "stylesheet" in attributes.get("rel", "").split():
            self.hrefs.append(attributes["href"])


class HomePageTests(SimpleTestCase):
    def test_home_page_and_local_stylesheets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('lang="fa"', html)
        self.assertIn('dir="rtl"', html)

        parser = _StylesheetParser()
        parser.feed(html)
        self.assertEqual(len(parser.hrefs), 4)
        for href in parser.hrefs:
            relative_path = href
            if relative_path.startswith(settings.STATIC_URL):
                relative_path = relative_path[len(settings.STATIC_URL) :]
            else:
                relative_path = relative_path.lstrip("/")
                if relative_path.startswith(settings.STATIC_URL):
                    relative_path = relative_path[len(settings.STATIC_URL) :]
            with self.subTest(href=href):
                self.assertIsNotNone(finders.find(relative_path))

    def test_base_template_has_no_external_http_urls(self):
        template_path = Path(settings.BASE_DIR) / "templates" / "base.html"
        source = template_path.read_text(encoding="utf-8")
        self.assertNotIn("http://", source)
        self.assertNotIn("https://", source)
