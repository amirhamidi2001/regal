from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.accounts.managers import UserManager
from apps.core.models import TimeStampedModel
from apps.core.validators import MOBILE_PATTERN, normalize_mobile, validate_mobile


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    # ASSUMPTION: TimeStampedModel.created_at replaces Django's date_joined field.
    mobile = models.CharField(max_length=11, unique=True, validators=[validate_mobile])
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(mobile__regex=MOBILE_PATTERN),
                name="accounts_user_mobile_format",
            ),
        ]

    def save(self, *args, **kwargs):
        self.mobile = normalize_mobile(self.mobile)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.mobile

    def get_full_name(self):
        return self.full_name or self.mobile

    def get_short_name(self):
        return self.full_name or self.mobile
