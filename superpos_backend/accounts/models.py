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


# ── Universal Movement Ledger (Phase 1.5 Slice D) ────────────────────────────

class FinancialAccountMovement(models.Model):
    """Append-only ledger row for money flowing into/out of a FinancialAccount.

    MASTER_DATA_CONTRACT.md §6.3 (FinancialAccountMovement). Every posted
    document in later slices (sales, purchases, customer receipts,
    supplier payments, cash drops, expenses, …) will write one or more rows
    here through `accounts.services.account_movements`. Reports read from
    these rows, never from UI state.

    Sign convention:
        * `debit`  is always positive (Decimal >= 0)
        * `credit` is always positive (Decimal >= 0)
        * exactly one of (debit, credit) is non-zero per row (enforced by
          DB CHECK + service layer).

    For asset-like account types (cashbox/main_safe/bank/card_settlement/
    wallet/customer_ar/expense/opening_balance/other), debit increases the
    balance and credit decreases it. For liability-like accounts
    (supplier_ap) the rule flips: credit increases, debit decreases.
    Centralized in `account_movements.balance_delta()` so future AR/AP
    additions only touch one place.

    `balance_after` is computed by the service at write time using a
    `select_for_update()` lock on prior rows, so concurrent posts can't
    interleave and produce an out-of-order running balance.

    `source_document_type` + `source_document_id` are opaque pointers — the
    service writer is responsible for setting them; we deliberately do NOT
    FK to a generic content type so this table stays tenant-clean and
    cheaply indexable.

    `terminal_id` and `shift_id` are forward-declared as plain ints because
    Terminal exists today but Shift doesn't yet (lands in a later slice).
    A future migration can swap shift_id for a real FK without data loss.
    """

    class MovementType(models.TextChoices):
        OPENING_BALANCE          = 'opening_balance',          'Opening Balance'
        SALES_CASH_IN            = 'sales_cash_in',            'Sales Cash In'
        SALES_CARD_IN            = 'sales_card_in',            'Sales Card In'
        SALES_WALLET_IN          = 'sales_wallet_in',          'Sales Wallet In'
        SALES_CREDIT             = 'sales_credit',             'Sales Credit'
        CUSTOMER_RECEIPT_IN      = 'customer_receipt_in',      'Customer Receipt In'
        SALES_RETURN_OUT         = 'sales_return_out',         'Sales Return Out'
        PURCHASE_OUT             = 'purchase_out',             'Purchase Out'
        SUPPLIER_PAYMENT_OUT     = 'supplier_payment_out',     'Supplier Payment Out'
        SUPPLIER_AP_INCREASE     = 'supplier_ap_increase',     'Supplier AP Increase'
        PURCHASE_RETURN_IN       = 'purchase_return_in',       'Purchase Return In'
        EXPENSE_OUT              = 'expense_out',              'Expense Out'
        EXPENSE_RECORDED         = 'expense_recorded',         'Expense Recorded'
        CASH_IN                  = 'cash_in',                  'Cash In'
        CASH_OUT                 = 'cash_out',                 'Cash Out'
        CASH_DROP_OUT            = 'cash_drop_out',            'Cash Drop Out'
        CASH_DROP_IN             = 'cash_drop_in',             'Cash Drop In'
        SETTLEMENT_TO_BANK       = 'settlement_to_bank',       'Settlement To Bank'
        SETTLEMENT_FROM_CARD     = 'settlement_from_card',     'Settlement From Card'
        ROUNDING_ADJUSTMENT      = 'rounding_adjustment',      'Rounding Adjustment'
        OTHER                    = 'other',                    'Other'

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='account_movements', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT,
        related_name='account_movements', db_index=True,
        # Nullable because a tenant-wide account (e.g. headquarters bank)
        # may receive a movement that isn't anchored to a specific branch.
        null=True, blank=True,
    )
    account = models.ForeignKey(
        FinancialAccount, on_delete=models.PROTECT,
        related_name='movements',
    )
    source_document_type = models.CharField(max_length=80, blank=True, default='')
    source_document_id   = models.BigIntegerField(null=True, blank=True)
    movement_type        = models.CharField(
        max_length=40, choices=MovementType.choices, db_index=True,
    )
    debit         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=18, decimal_places=2)
    currency      = models.CharField(max_length=8, blank=True, default='')
    actor_user    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='account_movements',
    )
    terminal_id   = models.BigIntegerField(null=True, blank=True)
    shift_id      = models.BigIntegerField(null=True, blank=True)
    occurred_at   = models.DateTimeField(db_index=True)
    notes         = models.CharField(max_length=255, blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['account_id', 'id']
        indexes = [
            models.Index(fields=['tenant', 'account', 'id'], name='acct_mvmt_t_a_id_idx'),
            models.Index(fields=['tenant', 'branch', 'occurred_at'], name='acct_mvmt_t_b_occ_idx'),
            models.Index(
                fields=['source_document_type', 'source_document_id'],
                name='acct_mvmt_src_idx',
            ),
        ]
        constraints = [
            # Both sides must be >= 0 …
            models.CheckConstraint(
                check=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name='acct_mvmt_nonneg',
            ),
            # … and exactly one side must be > 0. Encoded as: NOT (both > 0)
            # AND NOT (both == 0).
            models.CheckConstraint(
                check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)),
                name='acct_mvmt_one_side_only',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit=0) & models.Q(credit=0)),
                name='acct_mvmt_nonzero',
            ),
        ]

    def __str__(self):
        side = f'+{self.debit}' if self.debit else f'-{self.credit}'
        return f'Mvmt[{self.account_id}] {self.movement_type} {side} → {self.balance_after}'


# ── Customer + Supplier master data (Phase 1.5 Slice E) ──────────────────────

class _PartyBase(models.Model):
    """Shared columns for tenant-scoped party records (Customer / Supplier).

    Both parties are master data, not transactional records — the
    `opening_balance` field here is just a stored hint for future
    AR/AP slices and does NOT create any movement on its own.
    `default_branch` clears (SET_NULL) when the branch is removed so a
    branch deactivation never blocks party records.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='%(class)ss', db_index=True,
    )
    code = models.CharField(max_length=40, blank=True, default='', db_index=True)
    name = models.CharField(max_length=160)
    phone      = models.CharField(max_length=50, blank=True, default='')
    email      = models.EmailField(blank=True, default='')
    tax_number = models.CharField(max_length=64, blank=True, default='')
    default_branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['name']


class Customer(_PartyBase):
    """Tenant-scoped customer record.

    `credit_limit` and `price_tier_id` are stored hints for later slices
    (credit sales, price tier resolution) — neither is enforced yet.
    `price_tier_id` is a forward-declared plain BigInt because PriceTier
    doesn't exist as a model in this slice; a later migration can swap
    the column for a proper FK without data loss.
    """

    credit_limit  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_tier_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            # Per-tenant code uniqueness when set. Empty default '' is
            # allowed across many rows so walk-in / unnamed parties don't
            # collide.
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                condition=~models.Q(code=''),
                name='accounts_customer_tenant_code_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.name} (Customer)'


class Supplier(_PartyBase):
    """Tenant-scoped supplier record. Same shape as Customer minus
    credit/price-tier hints (suppliers don't have credit limits in our
    direction — that's the tenant's AP exposure, modeled by the
    `supplier_ap` FinancialAccount type)."""

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                condition=~models.Q(code=''),
                name='accounts_supplier_tenant_code_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.name} (Supplier)'


# ── Customer AR + Supplier AP Movement Ledgers (Phase 1.5 Slice F) ──────────

class _PartyMovementBase(models.Model):
    """Shared columns for party-balance ledgers (CustomerARMovement /
    SupplierAPMovement).

    Same sign convention as `FinancialAccountMovement`:
        * `debit`  >= 0
        * `credit` >= 0
        * exactly one is > 0 per row (DB CHECK + service-layer guard)

    Direction (asset vs liability) is *not* encoded on the row — the
    service layer decides via `balance_delta()` so the column meaning
    stays consistent across all ledgers and reports.

    `source_document_type` / `source_document_id` are opaque pointers
    the future posting engine sets (SalesInvoice, CustomerReceipt,
    PurchaseInvoice, SupplierPayment, …). Stored as plain strings/ints
    rather than a generic content-type FK to keep this table cheap.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='+', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT,
        related_name='+', db_index=True,
        null=True, blank=True,
    )
    source_document_type = models.CharField(max_length=80, blank=True, default='')
    source_document_id   = models.BigIntegerField(null=True, blank=True)
    movement_type        = models.CharField(max_length=40, db_index=True)
    debit         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=18, decimal_places=2)
    currency      = models.CharField(max_length=8, blank=True, default='')
    actor_user    = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    occurred_at   = models.DateTimeField(db_index=True)
    notes         = models.CharField(max_length=255, blank=True, default='')
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['id']


class CustomerARMovement(_PartyMovementBase):
    """Append-only AR ledger row for one customer.

    Asset-like rule (encoded in `accounts.services._party_ledger`):
        debit  → increases customer balance (customer owes more)
        credit → decreases customer balance (customer paid or settled)

    Writes go through `accounts.services.customer_ar` exclusively in this
    slice — no public POST API.
    """

    class MovementType(models.TextChoices):
        OPENING_BALANCE     = 'opening_balance',     'Opening Balance'
        SALES_CREDIT        = 'sales_credit',        'Sales Credit'
        CUSTOMER_RECEIPT    = 'customer_receipt',    'Customer Receipt'
        SALES_RETURN        = 'sales_return',        'Sales Return'
        WRITE_OFF           = 'write_off',           'Write Off'
        ADJUSTMENT          = 'adjustment',          'Adjustment'
        OVERPAYMENT_REFUND  = 'overpayment_refund',  'Overpayment Refund'
        OTHER               = 'other',               'Other'

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name='ar_movements',
    )

    class Meta:
        ordering = ['customer_id', 'id']
        indexes = [
            models.Index(fields=['tenant', 'customer', 'id'], name='ar_mvmt_t_c_id_idx'),
            models.Index(fields=['tenant', 'branch', 'occurred_at'], name='ar_mvmt_t_b_occ_idx'),
            models.Index(
                fields=['source_document_type', 'source_document_id'],
                name='ar_mvmt_src_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name='ar_mvmt_nonneg',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)),
                name='ar_mvmt_one_side_only',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit=0) & models.Q(credit=0)),
                name='ar_mvmt_nonzero',
            ),
        ]

    def __str__(self):
        side = f'+{self.debit}' if self.debit else f'-{self.credit}'
        return f'AR[{self.customer_id}] {self.movement_type} {side} → {self.balance_after}'


class SupplierAPMovement(_PartyMovementBase):
    """Append-only AP ledger row for one supplier.

    Liability-like rule (encoded in `accounts.services._party_ledger`):
        credit → increases supplier balance (we owe more)
        debit  → decreases supplier balance (we paid or returned)
    """

    class MovementType(models.TextChoices):
        OPENING_BALANCE   = 'opening_balance',   'Opening Balance'
        PURCHASE_CREDIT   = 'purchase_credit',   'Purchase Credit'
        SUPPLIER_PAYMENT  = 'supplier_payment',  'Supplier Payment'
        PURCHASE_RETURN   = 'purchase_return',   'Purchase Return'
        SUPPLIER_ADVANCE  = 'supplier_advance',  'Supplier Advance'
        WRITE_OFF         = 'write_off',         'Write Off'
        ADJUSTMENT        = 'adjustment',        'Adjustment'
        OTHER             = 'other',             'Other'

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT,
        related_name='ap_movements',
    )

    class Meta:
        ordering = ['supplier_id', 'id']
        indexes = [
            models.Index(fields=['tenant', 'supplier', 'id'], name='ap_mvmt_t_s_id_idx'),
            models.Index(fields=['tenant', 'branch', 'occurred_at'], name='ap_mvmt_t_b_occ_idx'),
            models.Index(
                fields=['source_document_type', 'source_document_id'],
                name='ap_mvmt_src_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name='ap_mvmt_nonneg',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit__gt=0) & models.Q(credit__gt=0)),
                name='ap_mvmt_one_side_only',
            ),
            models.CheckConstraint(
                check=~(models.Q(debit=0) & models.Q(credit=0)),
                name='ap_mvmt_nonzero',
            ),
        ]

    def __str__(self):
        side = f'+{self.debit}' if self.debit else f'-{self.credit}'
        return f'AP[{self.supplier_id}] {self.movement_type} {side} → {self.balance_after}'


# ── Settlement Documents (Phase 1.5 Slice G) ─────────────────────────────────
#
# CustomerReceipt and SupplierPayment are the first real *settlement
# documents* in the system. Each one is a small header record whose
# successful create-and-post produces:
#   * one document row (this table), plus
#   * one party-ledger row (CustomerARMovement / SupplierAPMovement), plus
#   * one finance-ledger row (FinancialAccountMovement)
#
# All three are written inside a single atomic transaction by the posting
# service so partial postings are impossible (see
# `accounts/services/customer_receipts.py` and `supplier_payments.py`).
#
# Status model:
#   This slice ships POSTED only. The existing transactional shape in the
#   codebase doesn't carry a generic cancel/reverse pattern yet, so we
#   intentionally keep it minimal — `posted_at` records the post timestamp
#   and the row is immutable thereafter. Future slices that need to undo a
#   receipt/payment will post a *compensating* document (sign-flipped
#   ledger rows), not mutate this one. That keeps the audit trail honest.

class _SettlementDocumentBase(models.Model):
    """Shared columns for settlement documents (CustomerReceipt /
    SupplierPayment).

    Both documents share an identical header shape — only the party FK and
    the account-side semantics differ. Centralising the shared columns here
    keeps the per-document model files terse and lets a future slice add
    fields (e.g. `currency`, `exchange_rate`, `posted_by_terminal`) in one
    place.
    """

    class Status(models.TextChoices):
        POSTED = 'posted', 'Posted'

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='+', db_index=True,
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT,
        related_name='+', db_index=True,
        null=True, blank=True,
    )
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT,
        related_name='+',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True, default='')
    notes     = models.CharField(max_length=255, blank=True, default='')
    status    = models.CharField(
        max_length=10, choices=Status.choices,
        default=Status.POSTED, db_index=True,
    )
    posted_at = models.DateTimeField(db_index=True)
    actor_user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-id']


class CustomerReceipt(_SettlementDocumentBase):
    """A customer's settlement of an outstanding AR balance.

    Posting flow (atomic — see `accounts.services.customer_receipts.create_customer_receipt`):
        1. CustomerReceipt row is created here.
        2. CustomerARMovement.credit posted against the customer (AR ↓).
        3. FinancialAccountMovement.debit posted against the destination
           account (cashbox / bank / wallet / card_settlement balance ↑).

    `destination_account` MUST be account-type compatible with the
    selected `payment_method.method_type`. The compatibility matrix lives
    in the serializer/service layer (mirrors the rules already enforced
    by `BranchPaymentMethodSerializer`). For credit-type methods, the
    destination_account would be customer_ar — but a "credit receipt"
    is nonsense (it'd be paying AR with AR), so credit methods are
    rejected at the service layer.
    """

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name='receipts',
    )
    destination_account = models.ForeignKey(
        FinancialAccount, on_delete=models.PROTECT,
        related_name='customer_receipts',
    )

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['tenant', 'customer', 'id'], name='cust_rcpt_t_c_id_idx'),
            models.Index(fields=['tenant', 'branch', 'posted_at'], name='cust_rcpt_t_b_pst_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='cust_rcpt_amount_positive',
            ),
        ]

    def __str__(self):
        return f'CustomerReceipt[{self.id}] {self.customer_id} {self.amount} ({self.status})'


class SupplierPayment(_SettlementDocumentBase):
    """A payment we made to settle an outstanding AP balance with a supplier.

    Posting flow (atomic — see `accounts.services.supplier_payments.create_supplier_payment`):
        1. SupplierPayment row is created here.
        2. SupplierAPMovement.debit posted against the supplier (AP ↓).
        3. FinancialAccountMovement.credit posted against the source
           account (cashbox / bank / wallet balance ↓).

    `source_account` MUST be account-type compatible — paying a supplier
    from a card_settlement account is not a meaningful real-world flow,
    so the service layer restricts source accounts to cashbox / bank /
    wallet / main_safe. Credit-type payment methods are rejected (a
    "credit payment to supplier" would be increasing AP, not settling it).
    """

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT,
        related_name='payments',
    )
    source_account = models.ForeignKey(
        FinancialAccount, on_delete=models.PROTECT,
        related_name='supplier_payments',
    )

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['tenant', 'supplier', 'id'], name='sup_pmt_t_s_id_idx'),
            models.Index(fields=['tenant', 'branch', 'posted_at'], name='sup_pmt_t_b_pst_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='sup_pmt_amount_positive',
            ),
        ]

    def __str__(self):
        return f'SupplierPayment[{self.id}] {self.supplier_id} {self.amount} ({self.status})'
