from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'organization', 'role', 'is_staff']
    list_filter = ['role', 'organization', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('BreatheESG', {'fields': ('organization', 'role')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('BreatheESG', {'fields': ('organization', 'role')}),
    )
