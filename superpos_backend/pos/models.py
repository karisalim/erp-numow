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
    # Stock tracked as Decimal so weighted SKUs (0.5 kg) deduct correctly.
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
    qty           = models.DecimalField(max_digits=8, decimal_places=3)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    sale          = models.ForeignKey(
        Sale, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='movements',
    )
    note          = models.CharField(max_length=200, blank=True, default='')

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
