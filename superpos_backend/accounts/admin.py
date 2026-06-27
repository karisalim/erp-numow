from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Branch, Tenant, Terminal, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display  = ['name', 'plan', 'active', 'trial_ends_at', 'created_at']
    list_filter   = ['plan', 'active']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display  = ['name', 'tenant', 'phone', 'active', 'created_at']
    list_filter   = ['tenant', 'active']
    search_fields = ['name', 'tenant__name']
    autocomplete_fields = ['tenant']


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display  = ['name', 'branch', 'serial', 'active', 'created_at']
    list_filter   = ['branch__tenant', 'active']
    search_fields = ['name', 'serial', 'branch__name']
    autocomplete_fields = ['branch']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['username', 'email', 'get_full_name', 'role', 'tenant', 'branch', 'terminal', 'is_active']
    list_filter   = ['role', 'tenant', 'branch', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name','role']
    autocomplete_fields = ['tenant', 'branch', 'terminal']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('POS info', {'fields': ('role', 'tenant', 'branch', 'terminal', 'pin_code')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('POS info', {'fields': ('role', 'tenant', 'branch', 'terminal', 'pin_code')}),
    )
