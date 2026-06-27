from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models


class Tenant(models.Model):
    class Plan(models.TextChoices):
        STARTER    = 'starter',    'Starter'
        GROWTH     = 'growth',     'Growth'
        ENTERPRISE = 'enterprise', 'Enterprise'

    class PrinterConnection(models.TextChoices):
        USB       = 'usb',       'USB'
        NETWORK   = 'network',   'Network'
        BLUETOOTH = 'bluetooth', 'Bluetooth'

    class ScaleConnection(models.TextChoices):
        SERIAL  = 'serial',  'Serial'
        USB     = 'usb',     'USB'
        NETWORK = 'network', 'Network'

    class ScaleExportInterval(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        HOURLY = 'hourly', 'Hourly'
        DAILY  = 'daily',  'Daily'
        WEEKLY = 'weekly', 'Weekly'

    name           = models.CharField(max_length=255, unique=True)
    plan           = models.CharField(max_length=20, choices=Plan.choices, default=Plan.STARTER)
    trial_ends_at  = models.DateTimeField(null=True, blank=True)
    active         = models.BooleanField(default=True)
    # Allow multiple numbers separated by commas/dashes.
    phone          = models.CharField(max_length=255, blank=True, null=True)
    address        = models.TextField(blank=True, null=True)
    vat_number     = models.CharField(max_length=64, blank=True, null=True)
    logo           = models.ImageField(upload_to='tenant_logos/', blank=True, null=True)
    receipt_header       = models.TextField(blank=True, default='')
    receipt_footer       = models.TextField(blank=True, default='')

    # ── Localization ──────────────────────────────────────────────────────────
    currency             = models.CharField(max_length=8,  default='EGP')
    language             = models.CharField(max_length=8,  default='en')
    timezone             = models.CharField(max_length=64, default='Africa/Cairo')
    show_tax_on_receipt  = models.BooleanField(default=True)

    # ── Hardware: printer ─────────────────────────────────────────────────────
    printer_name       = models.CharField(max_length=120, blank=True, default='')
    printer_connection = models.CharField(
        max_length=12, choices=PrinterConnection.choices,
        default=PrinterConnection.USB,
    )
    printer_ip         = models.GenericIPAddressField(blank=True, null=True)

    # ── Hardware: scale ───────────────────────────────────────────────────────
    scale_barcode_prefix = models.CharField(max_length=4, default='21')
    scale_connection = models.CharField(
        max_length=12, choices=ScaleConnection.choices,
        default=ScaleConnection.SERIAL,
    )
    scale_export_interval = models.CharField(
        max_length=12, choices=ScaleExportInterval.choices,
        default=ScaleExportInterval.MANUAL,
    )

    # ── Payments ──────────────────────────────────────────────────────────────
    payment_cash_enabled   = models.BooleanField(default=True)
    payment_card_enabled   = models.BooleanField(default=True)
    payment_wallet_enabled = models.BooleanField(default=True)
    card_terminal_type     = models.CharField(max_length=64, blank=True, default='')

    # ── i18n: per-tenant translation overrides ────────────────────────────────
    # Keyed by language code (e.g. {"en": {...}, "ar": {...}}). Each value is a
    # flat key → string dict that overrides the bundled UI translations. Empty
    # dict means "use whatever the app ships with".
    translation_overrides = models.JSONField(default=dict, blank=True)

    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.plan})'


class Branch(models.Model):
    tenant     = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='branches')
    name       = models.CharField(max_length=255)
    address    = models.TextField(blank=True, default='')
    phone      = models.CharField(max_length=50, blank=True, default='')
    active     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'branches'
        unique_together     = ('tenant', 'name')
        ordering            = ['name']

    def __str__(self):
        return f'{self.tenant.name} — {self.name}'


class Terminal(models.Model):
    branch     = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='terminals')
    name       = models.CharField(max_length=255)
    serial     = models.CharField(max_length=255, unique=True, db_index=True)
    active     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('branch', 'name')
        ordering        = ['name']

    def __str__(self):
        return f'{self.branch.name} — {self.name} ({self.serial})'


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER   = 'Owner',   'Owner'
        ADMIN   = 'Admin',   'Admin'
        MANAGER = 'Manager', 'Manager'
        CASHIER = 'Cashier', 'Cashier'

    # Override `username` to drop the global UNIQUE — uniqueness is now
    # scoped per-tenant via the composite constraint in Meta below. Two
    # tenants can independently have a cashier called "ahmed".
    username = models.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text='Required. 150 chars or fewer. Unique per tenant.',
        error_messages={'unique': 'A user with that username already exists in this tenant.'},
    )

    role     = models.CharField(max_length=10, choices=Role.choices, default=Role.CASHIER)
    tenant   = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='users',
        null=True, blank=True,
    )
    branch   = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff',
    )
    terminal = models.ForeignKey(
        Terminal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users',
    )
    pin_code  = models.CharField(max_length=128, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering        = ['username']
        unique_together = [('tenant', 'username')]

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role})'

    # ── PIN helpers ────────────────────────────────────────────────────────────

    def set_pin(self, raw_pin: str) -> None:
        self.pin_code = make_password(str(raw_pin))

    def verify_pin(self, raw_pin: str) -> bool:
        return check_password(str(raw_pin), self.pin_code)

    def has_pin(self) -> bool:
        return bool(self.pin_code)
