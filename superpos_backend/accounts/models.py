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
    """Per-tenant physical or operational location.

    Phase 1.5 Slice A added the v3.6 master-data fields (code, branch_type,
    tax info, currency/timezone, is_main) so a tenant can configure each
    branch independently from the UI/API instead of having every branch
    inherit tenant-wide defaults. The legacy `active` flag remains the
    single source of truth for "branch is operational"; the API surface
    exposes it as `is_active` (MASTER_DATA_CONTRACT.md §4.3) — see
    `BranchSerializer`.
    """

    class BranchType(models.TextChoices):
        MAIN           = 'main',           'Main'
        STORE          = 'store',          'Store'
        WAREHOUSE_ONLY = 'warehouse_only', 'Warehouse Only'
        DELIVERY       = 'delivery',       'Delivery'
        KIOSK          = 'kiosk',          'Kiosk'
        OTHER          = 'other',          'Other'

    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='branches')
    name        = models.CharField(max_length=255)
    code        = models.CharField(max_length=40, blank=True, default='', db_index=True)
    branch_type = models.CharField(
        max_length=20, choices=BranchType.choices,
        default=BranchType.STORE,
    )
    address     = models.TextField(blank=True, default='')
    phone       = models.CharField(max_length=50, blank=True, default='')
    tax_number  = models.CharField(max_length=64, blank=True, default='')
    currency    = models.CharField(max_length=8,  blank=True, default='')
    timezone    = models.CharField(max_length=64, blank=True, default='')
    is_main     = models.BooleanField(default=False)
    active      = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'branches'
        # `name` stays globally unique-per-tenant (legacy). `code` is also
        # unique-per-tenant *when set*; the partial constraint lets two
        # branches both carry the legacy empty default ''.
        unique_together     = ('tenant', 'name')
        ordering            = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                condition=~models.Q(code=''),
                name='accounts_branch_tenant_code_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.tenant.name} — {self.name}'

    # ── Convenience ───────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """API-facing alias for the legacy `active` field.

        The v3.6 master-data contract names this `is_active`; the DB column
        stays `active` so existing migrations and ORM call-sites keep working.
        """
        return self.active


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


# ── Branch master-data foundation (Phase 1.5 Slice A) ────────────────────────

class BranchSettings(models.Model):
    """Per-branch operational defaults.

    MASTER_DATA_CONTRACT.md §4.3 model shape. Most of the "default account"
    pointers reference models that don't exist yet (warehouses, cashboxes,
    price tiers — those land in later slices). Storing them as nullable
    BigIntegers keeps this migration safely additive: when the target
    models exist, a later migration can swap each `*_id` for a proper
    `ForeignKey` without data loss.

    Created lazily on first GET — see `BranchSettingsView.get_object`.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='branch_settings', db_index=True,
    )
    branch = models.OneToOneField(
        Branch, on_delete=models.CASCADE,
        related_name='settings',
    )

    # Forward-declared FKs — stored as plain ids until the target tables exist.
    default_sales_warehouse_id    = models.BigIntegerField(null=True, blank=True)
    default_purchase_warehouse_id = models.BigIntegerField(null=True, blank=True)
    default_cashbox_id            = models.BigIntegerField(null=True, blank=True)
    default_main_safe_id          = models.BigIntegerField(null=True, blank=True)
    default_price_tier_id         = models.BigIntegerField(null=True, blank=True)

    # Behavior toggles
    require_shift_for_pos              = models.BooleanField(default=False)
    allow_negative_stock               = models.BooleanField(default=False)
    allow_shift_close_with_open_orders = models.BooleanField(default=False)

    # Receipt customization (overrides the tenant-wide values when set)
    receipt_header = models.TextField(blank=True, default='')
    receipt_footer = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'branch settings'

    def __str__(self):
        return f'Settings for {self.branch}'


class BranchUserAssignment(models.Model):
    """Maps a user to a branch with a per-branch role.

    A user can be assigned to many branches; the legacy `User.branch` FK
    keeps representing the user's default/primary branch. `is_default_branch`
    here mirrors that intent at the assignment level and lets the assignment
    table answer "all branches this user can operate in" without rewriting
    the legacy user shape.

    MASTER_DATA_CONTRACT.md §4.3 model shape.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='branch_user_assignments', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE,
        related_name='user_assignments',
    )
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='branch_assignments',
    )
    # Reuses the existing User.Role vocabulary for consistency. Stored as a
    # plain CharField (not FK) so the constraint matches Django convention.
    role_at_branch = models.CharField(
        max_length=10, choices=User.Role.choices,
        default=User.Role.CASHIER,
    )
    is_default_branch = models.BooleanField(default=False)
    is_active         = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'branch user assignments'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'branch', 'user'],
                name='accounts_branch_user_uniq',
            ),
        ]
        ordering = ['branch_id', 'user_id']

    def __str__(self):
        return f'{self.user} @ {self.branch} ({self.role_at_branch})'


# ── Finance master data (Phase 1.5 Slice C) ──────────────────────────────────

class FinancialAccount(models.Model):
    """Tenant-scoped financial destination for money movements.

    Implements MASTER_DATA_CONTRACT.md §1.3 (FinancialAccount). Every
    `FinancialAccountMovement` in later slices points at one of these rows;
    `BranchPaymentMethod.destination_account` resolves the routing target so
    payment posting never guesses based on method name.

    Branch is optional: a tenant can keep tenant-wide accounts (e.g. a
    single bank account shared across branches) or define per-branch
    cashboxes. Account-type ↔ method-type compatibility is enforced at the
    `BranchPaymentMethod` serializer layer, not here, so an account row can
    be repurposed without rewriting history.
    """

    class AccountType(models.TextChoices):
        CASHBOX         = 'cashbox',         'Cashbox'
        MAIN_SAFE       = 'main_safe',       'Main Safe'
        BANK            = 'bank',            'Bank'
        CARD_SETTLEMENT = 'card_settlement', 'Card Settlement'
        WALLET          = 'wallet',          'Wallet'
        CUSTOMER_AR     = 'customer_ar',     'Customer AR'
        SUPPLIER_AP     = 'supplier_ap',     'Supplier AP'
        EXPENSE         = 'expense',         'Expense'
        OPENING_BALANCE = 'opening_balance', 'Opening Balance'
        OTHER           = 'other',           'Other'

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='financial_accounts', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT,
        null=True, blank=True, related_name='financial_accounts',
    )
    code            = models.CharField(max_length=40, blank=True, default='', db_index=True)
    name            = models.CharField(max_length=120)
    account_type    = models.CharField(
        max_length=20, choices=AccountType.choices, db_index=True,
    )
    currency        = models.CharField(max_length=8,  blank=True, default='')
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            # Per-tenant codes are unique when set. Empty default '' is
            # allowed across many rows so existing fixtures don't collide.
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                condition=~models.Q(code=''),
                name='accounts_financial_account_tenant_code_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'account_type'], name='accounts_facct_type_idx'),
        ]

    def __str__(self):
        return f'{self.name} [{self.account_type}]'


class PaymentMethod(models.Model):
    """Tenant-defined payment method (Cash / Card / Wallet / Credit / Custom).

    MASTER_DATA_CONTRACT.md §1.3 (PaymentMethod). A tenant can carry several
    methods of the same `method_type` (e.g. separate "Visa", "MasterCard",
    "Meeza" card methods that each settle into different accounts).

    Branch-specific destination routing lives on `BranchPaymentMethod`.
    """

    class MethodType(models.TextChoices):
        CASH   = 'cash',   'Cash'
        CARD   = 'card',   'Card'
        WALLET = 'wallet', 'Wallet'
        CREDIT = 'credit', 'Credit'
        CUSTOM = 'custom', 'Custom'

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='payment_methods', db_index=True,
    )
    name              = models.CharField(max_length=80)
    method_type       = models.CharField(
        max_length=10, choices=MethodType.choices, db_index=True,
    )
    provider_name     = models.CharField(max_length=80, blank=True, default='')
    # Credit defaults to requiring a customer; other types default to False.
    # Serializer auto-applies on create unless caller overrides explicitly.
    requires_customer = models.BooleanField(default=False)
    is_active         = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='accounts_payment_method_tenant_name_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.method_type})'

    def save(self, *args, **kwargs):
        # `credit` payment methods MUST always require a customer — a credit
        # sale without a customer has no AR target. Enforce at the model
        # layer so direct ORM writes (signals, fixtures, future services)
        # can't slip through the serializer-only check.
        if self.method_type == self.MethodType.CREDIT:
            self.requires_customer = True
        super().save(*args, **kwargs)


class BranchPaymentMethod(models.Model):
    """Per-branch enablement + routing for a payment method.

    MASTER_DATA_CONTRACT.md §1.3 (BranchPaymentMethod) — the **source of
    truth** for "where does this payment land?". A branch can enable a
    given `PaymentMethod` exactly once (unique per branch+method); the
    `destination_account` decides the FinancialAccount the money lands in.
    Card settlements may additionally point at a `settlement_bank_account`
    (where the acquirer ultimately pays out) and a
    `commission_expense_account` (where card fees post).

    All FK linkages must stay within the same tenant — enforced at the
    serializer layer, not via a DB CHECK, because Django would have to
    materialize the joined tenant id which is awkward without triggers.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='branch_payment_methods', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE,
        related_name='payment_methods',
    )
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT,
        related_name='branch_links',
    )
    destination_account = models.ForeignKey(
        FinancialAccount, on_delete=models.PROTECT,
        related_name='inbound_payment_methods',
    )
    settlement_bank_account = models.ForeignKey(
        FinancialAccount, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='settlement_payment_methods',
    )
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
    )
    fixed_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
    )
    commission_expense_account = models.ForeignKey(
        FinancialAccount, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='commission_payment_methods',
    )
    is_default = models.BooleanField(default=False)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['branch_id', 'payment_method_id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'branch', 'payment_method'],
                name='accounts_branch_payment_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.branch} :: {self.payment_method} -> {self.destination_account}'
