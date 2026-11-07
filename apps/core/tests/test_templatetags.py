from datetime import date, datetime, timezone
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.core.models import TimeStampedModel


class RegalTemplateFiltersTests(SimpleTestCase):
    def render(self, template, **context):
        return Template(template).render(Context(context))

    def test_filters_render_plain_text(self):
        output = self.render(
            "{% load regal %}{{ digits|persian_digits }}|{{ amount|toman }}|"
            "{{ day|jdate }}|{{ day|jdate:'long' }}|{{ moment|jdatetime_fa }}",
            digits="09",
            amount=104000,
            day=date(2026, 11, 4),
            moment=datetime(2026, 11, 4, 9, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(
            output,
            "۰۹|۱۰۴٬۰۰۰ تومان|۱۴۰۵/۰۸/۱۳|۱۳ آبان ۱۴۰۵|۱۴۰۵/۰۸/۱۳ ۱۲:۳۵",
        )

    def test_toman_none_is_blank_and_other_non_int_raises(self):
        self.assertEqual(self.render("{% load regal %}{{ value|toman }}", value=None), "")
        with self.assertRaises(TypeError):
            self.render("{% load regal %}{{ value|toman }}", value=Decimal("10"))

    def test_timestamp_model_is_abstract(self):
        self.assertIs(TimeStampedModel._meta.abstract, True)
