from django.contrib.auth.base_user import BaseUserManager

from apps.core.validators import normalize_mobile


class UserManager(BaseUserManager):
    def create_user(self, mobile, password=None, **extra_fields):
        mobile = normalize_mobile(mobile)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(mobile=mobile, **extra_fields)
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password=None, **extra_fields):
        if password is None:
            raise ValueError("A password is required to create a superuser.")
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self.create_user(mobile, password=password, **extra_fields)
