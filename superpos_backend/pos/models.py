import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction


class InsufficientStockError(Exception):
    """Raised by Product.deduct_stock when stock < qty.

    The serializer is allowed to catch this and emit a structured warning, but
    by default sale creation rolls back so we never write a half-applied sale.
    """

    def __init__(self, product, requested, available):
        self.product = product
        self.requested = requested
        self.available = available
        super().__init__(
            f'Insufficient stock for "{product.name}": '
            f'requested={requested}, available={available}',
        )


class Category(models.Model):
    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='categories', db_index=True,
    )
    name       = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering            = ['name']
        unique_together     = ('tenant', 'name')

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        PIECE  = 'piece',  'Piece'
        KG     = 'kg',     'Kilogram'
        LITER  = 'liter',  'Liter'
        CARTON = 'carton', 'Carton'

    tenant   = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='products', db_index=True,
    )
    barcode  = models.CharField(max_length=30, db_index=True)
    sku      = models.CharField(max_length=40, db_index=True)
    name     = models.CharField(max_length=120)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    cost     = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.10)
    # Global cached on-hand quantity (tenant-wide, NOT per-warehouse). Decimal
    # so weighted SKUs (0.5 kg) deduct correctly. Warehouse-aware movements
    # (SaleItem.warehouse / StockMovement.warehouse) record WHERE stock moved
    # for traceability, but this single counter remains the authoritative
    # quantity — per-warehouse stock balances are deferred to a future slice.
    stock    = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    reorder  = models.DecimalField(max_digits=10, decimal_places=3, default=10)
    color    = models.CharField(max_length=20, default='#6B7280')
    weighted = models.BooleanField(default=False)
    unit     = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    # Pieces contained in one sellable unit — useful for cartons / multi-packs.
    pack_qty = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    plu      = models.CharField(max_length=10, blank=True, default='')
    active   = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['name']
        unique_together = [('tenant', 'barcode'), ('tenant', 'sku')]
        indexes = [
            # Partial: fast lookups for the "low stock alerts" widget on the
            # dashboard — avoids scanning the whole catalog every page load.
            models.Index(
                fields=['tenant', 'stock'],
                name='pos_product_lowstock_idx',
                condition=models.Q(stock__lte=models.F('reorder')) & models.Q(active=True),
            ),
        ]
        # Database-level invariants — these are the last line of defense in
        # case application code (serializers, signals, raw SQL) ever forgets
        # to validate them.
        # Note: there is intentionally NO `stock >= 0` constraint. Oversell
        # is part of the business spec (FLOW.md, SaleSerializer docstring) —
        # the cashier may sell beyond on-hand stock; the row goes negative
        # and a warning is returned. A CHECK here would block that path.
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0),   name='pos_product_price_nonneg'),
            models.CheckConstraint(
                check=models.Q(tax_rate__gte=0) & models.Q(tax_rate__lte=1),
                name='pos_product_tax_rate_bounded',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def margin(self):
        if self.price:
            return round((self.price - self.cost) / self.price * 100, 1)
        return 0

    # ── Thread-safe stock helpers ─────────────────────────────────────────────

    def deduct_stock(self, qty, *, allow_oversell: bool = False, note: str = '') -> Decimal:
        """Atomically reduce this product's stock by `qty`.

        Wraps the read+write in `select_for_update()` inside a transaction so
        two concurrent checkouts can't both pass a "we have 1 left" check and
        oversell. Raises `InsufficientStockError` when stock < qty unless the
        caller explicitly opts in to negative stock (e.g. a sale flagged
        offline-late-sync where we already promised the customer the goods).
        """
        amount = Decimal(qty)
        if amount <= 0:
            raise ValueError('qty must be positive')

        with transaction.atomic():
            locked = Product.objects.select_for_update().get(pk=self.pk)
            if locked.stock < amount and not allow_oversell:
                raise InsufficientStockError(locked, amount, locked.stock)
            locked.stock = locked.stock - amount
            locked.save(update_fields=['stock', 'updated_at'])
            # Mirror the change onto `self` so callers don't see a stale row.
            self.stock = locked.stock
            _ = note
            return locked.stock


class InventoryBatch(models.Model):
    tenant             = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='inventory_batches', db_index=True,
    )
    product            = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    batch_number       = models.CharField(max_length=100)
    remaining_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    expiry_date        = models.DateField(null=True, blank=True)
    cost_price         = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    received_at        = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['expiry_date']
        verbose_name        = 'inventory batch'
        verbose_name_plural = 'inventory batches'

    def __str__(self):
        return f'{self.product.name} · batch {self.batch_number} ({self.remaining_quantity})'


class Sale(models.Model):
    class Method(models.TextChoices):
        CASH   = 'cash',   'Cash'
        CARD   = 'card',   'Card'
        WALLET = 'wallet', 'Wallet'
        CREDIT = 'credit', 'Credit'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        VOIDED    = 'voided',    'Voided'
        REFUNDED  = 'refunded',  'Refunded'

    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Percent'
        FIXED   = 'fixed',   'Fixed'

    tenant   = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='sales', db_index=True,
    )
    sale_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    cashier  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='sales',
    )
    # `branch` is required — every sale belongs to exactly one store. Legacy
    # NULL rows are backfilled in migration `0012_backfill_branches_and_enforce_sale_branch`
    # before the NOT NULL constraint is set. PROTECT prevents accidental
    # deletion of a branch that has historical sales.
    branch   = models.ForeignKey(
        'accounts.Branch', on_delete=models.PROTECT,
        related_name='sales',
    )
    terminal = models.ForeignKey(
        'accounts.Terminal', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales',
    )
    # Credit (AR) sales reference the customer who owes the balance. Nullable
    # so cash/card/wallet sales (the common case) stay exactly as before.
    customer = models.ForeignKey(
        'accounts.Customer', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sales',
    )
    subtotal   = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total      = models.DecimalField(max_digits=10, decimal_places=2)
    method     = models.CharField(max_length=10, choices=Method.choices)
    # Fast-indexed mirror of Payment.method so reporting queries don't need
    # to JOIN the Payment table. Authoritative source is Payment.method.
    payment_method_hint = models.CharField(
        max_length=10, choices=Method.choices, blank=True, default='',
    )
    paid       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status     = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    discount_type  = models.CharField(
        max_length=10, choices=DiscountType.choices, blank=True, null=True,
    )
    discount_value  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offline         = models.BooleanField(default=False)
    receipt_printed = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Tenant-scoped reporting (Sales page, dashboard) almost always
            # filters by tenant and orders by created_at DESC. A composite
            # index covers both in a single seek.
            models.Index(fields=['tenant', '-created_at'], name='pos_sale_tenant_recent_idx'),
            # Cashier-scoped lookups (RBAC cashier-own-sales filter).
            models.Index(fields=['cashier', '-created_at'], name='pos_sale_cashier_recent_idx'),
        ]

    def __str__(self):
        return f'SALE-{self.pk:06d}'


class SaleItem(models.Model):
    sale         = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product      = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=120)
    barcode      = models.CharField(max_length=30, blank=True, default='')
    qty          = models.DecimalField(max_digits=8, decimal_places=3)
    price_each   = models.DecimalField(max_digits=10, decimal_places=2)
    line_total   = models.DecimalField(max_digits=10, decimal_places=2)
    # Cost snapshot taken from Product.cost at sale time (Phase 1.5 Slice I).
    # Default 0 keeps the column additive; future COGS reporting reads it so
    # historical margin survives later cost changes.
    unit_cost    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Warehouse the stock left from (explicit per-line, or the branch's
    # default sales warehouse). Nullable so legacy rows / unconfigured tenants
    # are unaffected. Traceability only: this records WHERE the goods left from;
    # it does NOT maintain a per-warehouse balance — the on-hand quantity stays
    # on the global Product.stock (per-warehouse balances are a deferred slice).
    warehouse    = models.ForeignKey(
        'pos.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sale_items',
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product_name} x{self.qty}'


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        SALE_OUT    = 'sale_out',    'Sale Out'
        PURCHASE_IN = 'purchase_in', 'Purchase In'
        RECEIVE_IN  = 'receive_in',  'Receive In'
        RETURN_IN   = 'return_in',   'Return In'
        ADJUSTMENT  = 'adjustment',  'Adjustment'

    tenant        = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='stock_movements', db_index=True,
    )
    product       = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    # Per-branch inventory tracking — every movement must say which physical
    # location it affected. Stays nullable on the model so legacy rows survive
    # the migration; application code is expected to always set it on writes.
    branch        = models.ForeignKey(
        'accounts.Branch', on_delete=models.CASCADE,
        null=True, blank=True, related_name='stock_movements', db_index=True,
    )
    # Per-warehouse traceability (Phase 1.5 Dynamic Warehouses slice): records
    # which location this movement affected. It does NOT drive a per-warehouse
    # balance — the authoritative on-hand quantity is still the global
    # Product.stock counter; per-warehouse balances are deferred to a future
    # slice. Nullable for backward compatibility: legacy rows and existing
    # creation paths that don't pass a warehouse stay valid. SET_NULL (not
    # CASCADE) keeps this append-only ledger history intact if a warehouse
    # row is ever removed — though warehouses are deactivated, never deleted.
    warehouse     = models.ForeignKey(
        'pos.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements', db_index=True,
    )
    qty           = models.DecimalField(max_digits=8, decimal_places=3)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    sale          = models.ForeignKey(
        Sale, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='movements',
    )
    note          = models.CharField(max_length=200, blank=True, default='')

    # ── Running quantity ledger (Phase 1.5 stock-hardening slice) ───────────
    # `quantity_before` is the product's stock immediately before this
    # movement was applied; `quantity_after` is what it became after the
    # movement's signed delta landed. Together they let the frontend render
    # a real ledger column pair without recomputing anything.
    #
    # Both nullable so the additive migration lands without touching
    # legacy rows. New movements written through
    # `pos.services.stock_movements` always populate them; rows written
    # via the legacy serializer create-path keep NULL (statement summaries
    # tolerate the gap — see `get_product_stock_statement_summary`).
    quantity_before = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    quantity_after  = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    # ── Universal movement linkage (Phase 1.5 Slice D) ───────────────────────
    # `sale` above is a hard-coded FK to the legacy Sale model — it can't
    # represent a movement caused by a (future) PurchaseInvoice, OpenOrder,
    # ManualAdjustmentDoc, etc. MASTER_DATA_CONTRACT.md §6.3 requires every
    # movement to carry `source_document_type` + `source_document_id` so the
    # future posting engine can attach any document kind without hijacking
    # the legacy `sale` slot. `actor_user` is the operator audit pointer.
    # All three are nullable so legacy rows backfill to NULL cleanly.
    source_document_type = models.CharField(max_length=80, blank=True, default='')
    source_document_id   = models.BigIntegerField(null=True, blank=True)
    actor_user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='stock_movements',
    )

    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_movement_type_display()} | {self.product.name} | qty={self.qty}'


# ── Payments ─────────────────────────────────────────────────────────────────

class Payment(models.Model):
    """One-to-one payment record attached to a Sale.

    Keeps gateway/transaction metadata + the cash-tendered / change-given
    breakdown in a dedicated table so the Sale row stays lean for reporting.
    """

    class Method(models.TextChoices):
        CASH   = 'cash',   'Cash'
        CARD   = 'card',   'Card'
        WALLET = 'wallet', 'Wallet'
        CREDIT = 'credit', 'Credit'
        MIXED  = 'mixed',  'Mixed'

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        SUCCESS  = 'success',  'Success'
        FAILED   = 'failed',   'Failed'
        REFUNDED = 'refunded', 'Refunded'

    sale          = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='payment')
    method        = models.CharField(max_length=10, choices=Method.choices)
    status        = models.CharField(
        max_length=10, choices=Status.choices,
        default=Status.SUCCESS, db_index=True,
    )
    amount        = models.DecimalField(max_digits=10, decimal_places=2)
    gateway       = models.CharField(max_length=50, blank=True, null=True)
    transaction_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    amount_paid   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    change        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    requested_at  = models.DateTimeField(auto_now_add=True)
    processed_at  = models.DateTimeField(null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'Payment for sale={self.sale_id} ({self.method}/{self.status})'


# ── Audit Log ────────────────────────────────────────────────────────────────

class AuditLog(models.Model):
    """Append-only ledger of administrative changes for compliance.

    `old_values` and `new_values` are snapshotted dicts of model fields. The
    classmethod `log_change` is the only entry point app code should use —
    direct creation bypasses request-context extraction.
    """

    class Action(models.TextChoices):
        CREATE = 'create', 'Create'
        UPDATE = 'update', 'Update'
        DELETE = 'delete', 'Delete'
        VOID   = 'void',   'Void'

    tenant     = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='audit_logs', db_index=True,
    )
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_logs',
    )
    action     = models.CharField(max_length=10, choices=Action.choices)
    model_name = models.CharField(max_length=50, db_index=True)
    object_id  = models.BigIntegerField()
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    reason     = models.TextField(blank=True, default='')
    timestamp  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant', '-timestamp'], name='pos_audit_tenant_idx'),
            models.Index(fields=['model_name', 'object_id'], name='pos_audit_target_idx'),
        ]

    def __str__(self):
        return f'{self.action} {self.model_name}#{self.object_id} by user={self.user_id}'

    @classmethod
    def log_change(
        cls, *, tenant, user, action, model_name, object_id,
        new_values, old_values=None, request=None, reason='',
    ):
        """Persist an audit entry, pulling IP + UA from `request` when given."""
        ip = ''
        ua = ''
        if request is not None:
            ip = (
                request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                or request.META.get('REMOTE_ADDR', '')
                or ''
            )[:64]
            ua = request.META.get('HTTP_USER_AGENT', '') or ''
        return cls.objects.create(
            tenant=tenant, user=user, action=action,
            model_name=model_name, object_id=object_id,
            old_values=old_values, new_values=new_values or {},
            ip_address=ip, user_agent=ua, reason=reason or '',
        )


# ── Discount Codes / Coupons ─────────────────────────────────────────────────

class DiscountCode(models.Model):
    """Tenant-scoped coupon. `applicable_products` restricts the cart-line
    items that qualify; an empty M2M means "any product"."""

    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Percent'
        FIXED   = 'fixed',   'Fixed'

    tenant         = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='discount_codes', db_index=True,
    )
    code           = models.CharField(max_length=20, db_index=True)
    discount_type  = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from     = models.DateTimeField()
    valid_until    = models.DateTimeField()
    max_uses       = models.IntegerField(null=True, blank=True)
    uses_count     = models.IntegerField(default=0)
    min_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    applicable_products = models.ManyToManyField(Product, blank=True, related_name='discount_codes')
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['-valid_until']
        unique_together = [('tenant', 'code')]
        indexes = [
            models.Index(
                fields=['tenant', 'valid_until', 'is_active'],
                name='pos_discount_lookup_idx',
            ),
        ]

    def __str__(self):
        return f'{self.code} ({self.discount_type} {self.discount_value})'


# ── Idempotency ──────────────────────────────────────────────────────────────

class IdempotencyRecord(models.Model):
    """Stored fingerprint + response snapshot for a critical POST request.

    Implements API_CONTRACT.md §2 (Idempotency) and DOMAIN.md §6.3
    (Idempotency Rule). For every state-changing endpoint that opts in via
    `pos.services.idempotency`, the client supplies an `Idempotency-Key`
    header. The first successful invocation persists a row here with a
    deterministic hash of the request payload + the saved response status
    and body. Subsequent invocations with:

      * same key + same payload  → replay the stored response
      * same key + different payload → 409 conflict (callers raise it)

    Scoping is per-tenant: two tenants may legitimately use the same opaque
    key string without collision. `(tenant, key)` is unique to give an
    explicit DB-level guarantee on top of the service-layer check.

    Wire-up into endpoints is deferred — this slice only ships the
    scaffolding. See `pos/services/idempotency.py` for the helpers.
    """

    tenant = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='idempotency_records', db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='idempotency_records',
    )
    key            = models.CharField(max_length=255, db_index=True)
    method         = models.CharField(max_length=10)
    path           = models.CharField(max_length=255)
    request_hash   = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body  = models.JSONField(default=dict, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'key'],
                name='pos_idem_tenant_key_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'key'], name='pos_idem_tenant_key_idx'),
        ]

    def __str__(self):
        return f'Idem[{self.tenant_id}/{self.key}] {self.method} {self.path}'


# ── Dynamic Warehouses / Stores (Phase 1.5 foundation) ────────────────────────
# Backend foundation only — see MASTER_DATA_CONTRACT.md §5. A tenant defines
# warehouses/stores; branches link to them via BranchWarehouse with a role
# (sales, purchase_receiving, kitchen, …). No transfers / no posting here.

class Warehouse(models.Model):
    """A tenant-scoped stock location (store, kitchen, bar, damage bin, …).

    Linked to branches only through `BranchWarehouse` — this model is
    deliberately tenant-level with no direct branch FK so there is a single,
    unambiguous branch↔warehouse linking path. Deactivate (set
    `is_active=False`) instead of hard-deleting when referenced by movements.
    """

    class WarehouseType(models.TextChoices):
        MAIN         = 'main',         'Main'
        SALES        = 'sales',        'Sales'
        RAW_MATERIAL = 'raw_material', 'Raw Material'
        RETURNS      = 'returns',      'Returns'
        DAMAGE       = 'damage',       'Damage'
        PRODUCTION   = 'production',   'Production'
        OTHER        = 'other',        'Other'

    tenant         = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='warehouses', db_index=True,
    )
    code           = models.CharField(max_length=40, db_index=True)
    name           = models.CharField(max_length=255)
    warehouse_type = models.CharField(
        max_length=20, choices=WarehouseType.choices,
        default=WarehouseType.MAIN,
    )
    description    = models.TextField(blank=True, default='')
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            # `code` is a required human identifier and must be unique per
            # tenant (the same code may exist in a different tenant).
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                name='pos_warehouse_tenant_code_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'


class BranchWarehouse(models.Model):
    """Links a branch to a warehouse for a specific operational role.

    Role-based (per MASTER_DATA_CONTRACT.md §5.4.4): one warehouse can serve
    several roles for a branch (separate rows), and each (branch, role) has at
    most one active default. This is the canonical home for a branch's default
    sales/purchase/returns/damage warehouse.
    """

    class Role(models.TextChoices):
        SALES              = 'sales',              'Sales'
        PURCHASE_RECEIVING = 'purchase_receiving', 'Purchase Receiving'
        KITCHEN            = 'kitchen',            'Kitchen'
        BAR                = 'bar',                'Bar'
        RETURNS            = 'returns',            'Returns'
        DAMAGED            = 'damaged',            'Damaged'

    tenant     = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='branch_warehouses', db_index=True,
    )
    branch     = models.ForeignKey(
        'accounts.Branch', on_delete=models.CASCADE,
        related_name='branch_warehouses', db_index=True,
    )
    warehouse  = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE,
        related_name='branch_links', db_index=True,
    )
    role       = models.CharField(max_length=20, choices=Role.choices)
    is_default = models.BooleanField(default=False)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['branch_id', 'role']
        constraints = [
            # No duplicate *active* link for the same branch+warehouse+role.
            # Inactive (superseded) links are allowed to coexist as history.
            models.UniqueConstraint(
                fields=['tenant', 'branch', 'warehouse', 'role'],
                condition=models.Q(is_active=True),
                name='pos_branchwh_active_uniq',
            ),
            # At most one active default per (branch, role).
            models.UniqueConstraint(
                fields=['branch', 'role'],
                condition=models.Q(is_active=True, is_default=True),
                name='pos_branchwh_one_default_per_role',
            ),
        ]

    def __str__(self):
        return f'{self.branch_id}:{self.warehouse_id} [{self.role}]'


class WarehouseStock(models.Model):
    """Cached per-(product, warehouse) on-hand quantity (Phase 1.5 Slice J).

    Mirrors `Product.stock` (the global cached balance) one level down: one row
    per warehouse a product has moved through. The append-only `StockMovement`
    ledger stays the audit source of truth — this table is a fast,
    transactionally-maintained cache updated only through
    `pos.services.stock_movements.apply_warehouse_delta`.

    Only maintained when a movement carries a warehouse; legacy / unconfigured
    movements (warehouse=None) leave this table untouched, so the invariant is
    `Σ WarehouseStock(product) + unassigned == Product.stock`. Grounded in
    MASTER_DATA_CONTRACT.md §5 ("quantities tracked per product + unit +
    warehouse"); the product-unit dimension is deferred until ProductUnit exists.
    """

    tenant     = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='warehouse_stocks', db_index=True,
    )
    product    = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name='warehouse_stocks', db_index=True,
    )
    # PROTECT: warehouses are deactivated, never deleted — protecting the FK
    # keeps a balance from ever pointing at a vanished location.
    warehouse  = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT,
        related_name='stock_levels', db_index=True,
    )
    # Signed, may go negative — oversell is allowed exactly like the global
    # Product.stock (which intentionally carries no >= 0 constraint). 14/3
    # matches StockMovement's running-quantity columns.
    quantity   = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product_id', 'warehouse_id']
        constraints = [
            # Exactly one balance row per (tenant, product, warehouse); also the
            # get_or_create upsert key.
            models.UniqueConstraint(
                fields=['tenant', 'product', 'warehouse'],
                name='pos_warehousestock_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'warehouse'], name='pos_whstock_tenant_wh_idx'),
            models.Index(fields=['tenant', 'product'],   name='pos_whstock_tenant_prod_idx'),
        ]

    def __str__(self):
        return f'product={self.product_id} @ warehouse={self.warehouse_id} = {self.quantity}'


# ── Purchase Invoices (Phase 1.5 Slice H — posting foundation) ─────────────────
# Real posted purchase document for STOCK-ITEM lines only. Posting increases
# stock in a warehouse (+ moving-average cost on Product.cost), credits the
# source cash/bank account for the paid amount, and credits Supplier AP for
# the unpaid amount — all atomically. See pos/services/purchase_invoices.py.
#
# Accounting decisions for this slice (documented intentionally):
#   * Inventory is tracked by StockMovement quantity + Product.cost moving
#     average. There is NO Inventory GL FinancialAccount posting yet, so the
#     debit side of the purchase is represented by stock value, not a GL row.
#   * tax_amount / tax_total are STORED but NOT posted to any tax ledger —
#     v3.6 does not define purchase-tax accounting (DOMAIN §18 is sales-only).
#   * Only line_type='stock_item' is accepted for posting in this slice.

class PurchaseInvoice(models.Model):
    class PostingStatus(models.TextChoices):
        DRAFT  = 'draft',  'Draft'
        POSTED = 'posted', 'Posted'

    class PaymentStatus(models.TextChoices):
        UNPAID         = 'unpaid',         'Unpaid'
        PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
        PAID           = 'paid',           'Paid'

    tenant   = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='purchase_invoices', db_index=True,
    )
    branch   = models.ForeignKey(
        'accounts.Branch', on_delete=models.PROTECT,
        related_name='purchase_invoices', db_index=True,
    )
    supplier = models.ForeignKey(
        'accounts.Supplier', on_delete=models.PROTECT,
        related_name='purchase_invoices', db_index=True,
    )
    reference = models.CharField(max_length=120, blank=True, default='')

    # Totals — computed server-side from the lines during posting.
    subtotal       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total      = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Payment routing — both nullable (a fully-credit purchase needs neither).
    payment_method = models.ForeignKey(
        'accounts.PaymentMethod', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_invoices',
    )
    source_account = models.ForeignKey(
        'accounts.FinancialAccount', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_invoices',
    )

    posting_status = models.CharField(
        max_length=12, choices=PostingStatus.choices, default=PostingStatus.POSTED,
    )
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID,
    )
    posted_at  = models.DateTimeField(null=True, blank=True)
    actor_user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_invoices',
    )
    notes      = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', '-created_at'], name='pos_pinv_tenant_recent_idx'),
            models.Index(fields=['supplier', '-created_at'], name='pos_pinv_supplier_recent_idx'),
        ]

    def __str__(self):
        return f'PINV[{self.id}] {self.supplier_id} total={self.total_amount}'


class PurchaseInvoiceLine(models.Model):
    class LineType(models.TextChoices):
        STOCK_ITEM  = 'stock_item',  'Stock Item'
        EXPENSE     = 'expense',     'Expense'
        FIXED_ASSET = 'fixed_asset', 'Fixed Asset'
        SERVICE     = 'service',     'Service'
        NON_STOCK   = 'non_stock',   'Non Stock'

    tenant           = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='purchase_invoice_lines', db_index=True,
    )
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice, on_delete=models.CASCADE, related_name='lines',
    )
    product   = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        null=True, blank=True, related_name='purchase_invoice_lines',
    )
    # Resolved warehouse the stock landed in (may be auto-resolved from the
    # branch's default purchase_receiving link when omitted on input).
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='purchase_invoice_lines',
    )
    line_type       = models.CharField(
        max_length=20, choices=LineType.choices, default=LineType.STOCK_ITEM,
    )
    qty             = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost       = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount      = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total      = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes           = models.CharField(max_length=200, blank=True, default='')
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'PINVLine[{self.id}] {self.product_id} qty={self.qty}'


# ── Dynamic Units (Sprint 2 Batch 1 — MASTER_DATA_CONTRACT §2) ────────────────
# Tenant-defined measurement substrate. Units are DATA rows, never enums/choices
# (contract §2.5: "unit conversion is data-driven, not hard-coded"). Inventory
# quantities remain stored ONLY in the product's base unit (directive R-B) —
# nothing in this batch changes how Product.stock / StockMovement / WarehouseStock
# are denominated; the conversion layer is a pure service
# (pos/services/units.py). The legacy Product.unit enum + pack_qty stay intact
# and authoritative for behavior until the seed/cutover batches.


class UnitGroup(models.Model):
    """A measurement family per tenant (Mass, Volume, Count, Packaging, …).

    The group's base is the unit whose `factor_to_base` is exactly 1 (there is
    deliberately no `base_unit` FK — it would be circular with Unit; the
    factor-1 convention is service-validated instead).
    """

    tenant     = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='unit_groups', db_index=True,
    )
    name       = models.CharField(max_length=60)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='pos_unitgroup_tenant_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class Unit(models.Model):
    """A unit inside a group (g, kg, ml, L, piece, bottle, carton, bag, …).

    `factor_to_base` converts a quantity in this unit to the group's base unit
    (kg in a g-based Mass group → 1000). Packaging-style units (bottle, carton,
    bag) carry factor 1 and no cross-product meaning — their real conversion is
    per-product in `ProductUnit`.

    `allow_decimal` is the data-driven replacement for both the PIECE
    whole-number rule and the `weighted` flag (piece → False, g/ml/kg → True).
    It is plain data in this batch — sale-flow enforcement switches over only
    after a product's base ProductUnit is confirmed (Sprint 2 Batch 3+).
    """

    tenant        = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='units', db_index=True,
    )
    unit_group    = models.ForeignKey(
        UnitGroup, on_delete=models.PROTECT, related_name='units',
    )
    name          = models.CharField(max_length=60)
    symbol        = models.CharField(max_length=10, blank=True, default='')
    # Precision Decimal(16,6) per the approved Sprint 2 design (D-13 working
    # proposal). Convention: pick the smallest practical unit as each group's
    # base (g not kg, ml not L) so factors are >= 1 and almost always integral.
    factor_to_base = models.DecimalField(max_digits=16, decimal_places=6, default=1)
    allow_decimal  = models.BooleanField(default=True)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit_group_id', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'unit_group', 'name'],
                name='pos_unit_tenant_group_name_uniq',
            ),
            models.CheckConstraint(
                check=models.Q(factor_to_base__gt=0),
                name='pos_unit_factor_positive',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.symbol})' if self.symbol else self.name


class ProductUnit(models.Model):
    """Product-specific conversion layer: how one such unit of THIS product
    converts to the product's base unit.

    `conversion_to_base` is authoritative per product (contract §2.2): for milk
    with base ml, carton → 12000; for chocolate with base g, bag → 5000. It is
    seeded from `Unit.factor_to_base` when the unit shares the base's group,
    and free for packaging units (whose group factor is meaningless
    cross-product).

    Exactly one row per product may be the base (`is_base=True`, DB
    partial-unique) and its conversion must be exactly 1 (DB CHECK). Once
    StockMovements exist for a product, its base mapping is immutable — a
    re-denomination would silently reinterpret history (service guard in
    pos/services/units.py; an explicit re-denomination document is future
    scope).
    """

    tenant  = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='product_units', db_index=True,
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='product_units',
    )
    # PROTECT: a unit referenced by any product mapping is deactivated, never
    # deleted — deleting it would strand the conversion meaning.
    unit    = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name='product_units',
    )
    conversion_to_base = models.DecimalField(max_digits=16, decimal_places=6, default=1)
    is_base            = models.BooleanField(default=False)
    is_sale_unit       = models.BooleanField(default=False)
    is_purchase_unit   = models.BooleanField(default=False)
    # Recipe flag is plain data in this batch; consumed by the Recipe slice
    # (Sprint 3).
    is_recipe_unit     = models.BooleanField(default=False)
    is_active          = models.BooleanField(default=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product_id', '-is_base', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'product', 'unit'],
                name='pos_productunit_tenant_product_unit_uniq',
            ),
            # One base mapping per product — partial unique.
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_base=True),
                name='pos_productunit_one_base_per_product',
            ),
            models.CheckConstraint(
                check=models.Q(conversion_to_base__gt=0),
                name='pos_productunit_conversion_positive',
            ),
            # The base mapping is the identity by definition.
            models.CheckConstraint(
                check=~models.Q(is_base=True) | models.Q(conversion_to_base=1),
                name='pos_productunit_base_conversion_is_1',
            ),
        ]

    def __str__(self):
        flag = ' [base]' if self.is_base else ''
        return f'product={self.product_id} unit={self.unit_id} x{self.conversion_to_base}{flag}'


class ProductBarcodeUnit(models.Model):
    """A scannable barcode bound to one pack size of a product (R-K).

    Lets the carton and the single bottle each carry their own code. Barcodes
    are unique per tenant across THIS table; collisions against the legacy
    `Product.barcode` namespace are rejected at the serializer layer (the two
    columns cannot share a DB constraint). Scan-precedence wiring
    (ProductBarcodeUnit first, `Product.barcode` fallback) is Sprint 2 Batch 3
    — this batch only stores the mapping.
    """

    tenant       = models.ForeignKey(
        'accounts.Tenant', on_delete=models.CASCADE,
        related_name='product_barcode_units', db_index=True,
    )
    product      = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='barcode_units',
    )
    # CASCADE: a barcode names a pack definition; without the pack mapping the
    # code is meaningless.
    product_unit = models.ForeignKey(
        ProductUnit, on_delete=models.CASCADE, related_name='barcodes',
    )
    barcode      = models.CharField(max_length=64, db_index=True)
    is_default   = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product_id', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'barcode'],
                name='pos_pbu_tenant_barcode_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.barcode} -> product_unit={self.product_unit_id}'
