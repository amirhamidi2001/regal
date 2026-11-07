from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (
    AdminUserCreationForm as DjangoAdminUserCreationForm,
    UserChangeForm as DjangoUserChangeForm,
)
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class AdminUserCreationForm(DjangoAdminUserCreationForm):
    class Meta(DjangoAdminUserCreationForm.Meta):
        model = User
        fields = ("mobile", "full_name")


class UserChangeForm(DjangoUserChangeForm):
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("mobile", "password")}),
        (_("Personal info"), {"fields": ("full_name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("mobile", "full_name", "usable_password", "password1", "password2"),
            },
        ),
    )
    form = UserChangeForm
    add_form = AdminUserCreationForm
    list_display = ("mobile", "full_name", "is_staff", "is_active")
    search_fields = ("mobile", "full_name")
    ordering = ("-created_at",)
