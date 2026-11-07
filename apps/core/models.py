from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    # QuerySet.update() does not apply auto_now; callers using update() must set updated_at themselves.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
