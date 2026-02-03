from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.translation import gettext_lazy as _

from .models import Broker, Developer

User = get_user_model()

# Forms


class UserCreationForm(forms.ModelForm):
    """
    User creation form for the admin (with password confirmation).
    """
    password1 = forms.CharField(
        label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(
        label=_("Password confirmation"), widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "role")

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError(_("Passwords don't match."))
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """
    User edit form for the admin.
    The password is shown as a hashed readonly field.
    """
    password = ReadOnlyPasswordHashField(
        label=_("Password"),
        help_text=_(
            "Raw passwords are not stored, so there is no way to see this user's password.")
    )

    class Meta:
        model = User
        fields = (
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


# Inlines
class BrokerInline(admin.StackedInline):
    model = Broker
    extra = 0
    can_delete = True
    fields = ("is_verified", "verified_at", "verification_document")
    readonly_fields = ("verified_at",)


class DeveloperInline(admin.StackedInline):
    model = Developer
    extra = 0
    can_delete = True
    fields = ("company_name")


# Admins
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = ("email", "first_name", "last_name", "role",
                    "is_staff", "is_active", "date_joined")
    list_filter = ("role", "is_staff", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "role")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff",
         "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2", "is_staff", "is_superuser", "is_active"),
        }),
    )

    def get_inlines(self, request, obj=None):
        """
        Show BrokerInline only:
        - when editing an existing user,
        - and the user is a broker (by role or already has a broker profile).
        """
        if obj is None:
            return []
        
        role = getattr(obj, "role", None)
        if role == getattr(User, "Roles").BROKER or hasattr(obj, "broker"):
            return [BrokerInline]
        elif role == getattr(User, "Roles").DEVELOPER or hasattr(obj, "developer"):
            return [Developer]
        return []


@admin.register(Broker)
class BrokerAdmin(admin.ModelAdmin):
    list_display = ("user", "is_verified", "verified_at")
    list_filter = ("is_verified",)
    search_fields = ("user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)


@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name")
    search_fields = ("user__email", "user__first_name", "user__last_name", "company_name")
    autocomplete_fields = ("user",)
