import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from accounts.models import Branch
from .models import (
    BranchWarehouse, Category, InsufficientStockError, InventoryBatch,
    Payment, Product, Sale, SaleItem, StockMovement, Warehouse,
)

logger = logging.getLogger(__name__)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ['id', 'name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    margin        = serializers.FloatField(read_only=True)
    unit_display  = serializers.CharField(source='get_unit_display', read_only=True)

    class Meta:
        model  = Product
        fields = [
            'id', 'barcode', 'sku', 'name', 'category', 'category_name',
            'price', 'cost', 'tax_rate', 'stock', 'reorder', 'color',
            'weighted', 'unit', 'unit_display', 'pack_qty', 'plu', 'active',
            'margin', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductStockUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Product
        fields = ['stock']


class InventoryBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model  = InventoryBatch
        fields = [
            'id', 'product', 'product_name', 'batch_number',
            'remaining_quantity', 'expiry_date', 'cost_price', 'received_at', 'updated_at',
        ]
        read_only_fields = ['id', 'received_at', 'updated_at']


# ── Inventory action serializers ──────────────────────────────────────────────

class PurchaseReceiptSerializer(serializers.Serializer):
    product      = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    qty          = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal('0.001'))
    batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    expiry_date  = serializers.DateField(required=False, allow_null=True, default=None)
    cost_price   = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, default=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and getattr(request.user, 'tenant', None):
            self.fields['product'].queryset = Product.objects.filter(tenant=request.user.tenant)


class StockMovementSerializer(serializers.ModelSerializer):
    """Read + create stock movements.

    Create goes through `pos.services.stock_movements` so every new row
    carries `quantity_before` / `quantity_after` (the running ledger
    columns added in the stock-hardening slice). Bypassing the service
    would store NULL there and silently regress the statement summary,
    which is exactly the bug this serializer used to ship — direct
    `StockMovement.objects.create(**validated_data)` left both columns
    null even though the service knew how to populate them. The service
    also handles the row-level lock on `Product.stock`, so callers stop
    racing with `Product.deduct_stock` checkouts.

    The caller still passes a positive `qty` magnitude; direction is
    encoded by `movement_type`. ADJUSTMENT may carry a negative qty,
    which routes through `record_stock_out` (preserving the legacy
    serializer's accept-signed-qty behavior — see `create` for the
    full routing table).

    Read fields added by the stock-hardening slice:
        quantity_in / quantity_out — derived per-row magnitudes (use
            `abs(qty)` so legacy SALE_OUT rows with negative qty surface
            on the right side)
        quantity_before / quantity_after — running ledger balance pair
            populated by the service layer. Always read-only — clients
            cannot spoof balance fields by sending them in the payload.
    """

    product_name      = serializers.CharField(source='product.name', read_only=True)
    movement_type_display = serializers.CharField(
        source='get_movement_type_display', read_only=True,
    )
    quantity_in  = serializers.SerializerMethodField()
    quantity_out = serializers.SerializerMethodField()

    class Meta:
        model  = StockMovement
        fields = [
            'id', 'product', 'product_name', 'branch', 'warehouse',
            'qty', 'movement_type', 'movement_type_display',
            'quantity_in', 'quantity_out',
            'quantity_before', 'quantity_after',
            'source_document_type', 'source_document_id',
            'actor_user',
            'sale', 'note', 'created_at',
        ]
        read_only_fields = [
            'id', 'product_name', 'movement_type_display',
            'quantity_in', 'quantity_out',
            'quantity_before', 'quantity_after',
            'created_at',
        ]

    OUTFLOW_TYPES = {StockMovement.MovementType.SALE_OUT}

    # Direction-classification used to derive `quantity_in` / `quantity_out`
    # at read time. Kept in sync with `pos.services.stock_movements` —
    # ADJUSTMENT lives in both because the legacy schema collapses both
    # adjustment directions into one enum value.
    _IN_TYPES  = {
        StockMovement.MovementType.PURCHASE_IN,
        StockMovement.MovementType.RECEIVE_IN,
        StockMovement.MovementType.RETURN_IN,
        StockMovement.MovementType.ADJUSTMENT,
    }
    _OUT_TYPES = {
        StockMovement.MovementType.SALE_OUT,
        StockMovement.MovementType.ADJUSTMENT,
    }

    def get_quantity_in(self, obj):
        if obj.movement_type in self._OUT_TYPES:
            # ADJUSTMENT is in both sets — historical behavior treats it
            # as OUT for balance purposes, so quantity_in is 0 for those.
            return '0.000'
        if obj.movement_type in self._IN_TYPES:
            return f'{abs(obj.qty or Decimal("0")):.3f}'
        return '0.000'

    def get_quantity_out(self, obj):
        if obj.movement_type in self._OUT_TYPES:
            return f'{abs(obj.qty or Decimal("0")):.3f}'
        return '0.000'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and getattr(request.user, 'tenant', None):
            self.fields['product'].queryset = Product.objects.filter(tenant=request.user.tenant)
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=request.user.tenant)

    def validate_qty(self, value):
        if value == 0:
            raise serializers.ValidationError('Qty must be non-zero.')
        return value

    def validate_warehouse(self, value):
        """Warehouse (when supplied) must belong to the caller's tenant.

        Nullable on the model, so omitted/None is fine — but a supplied
        warehouse id from another tenant must not pollute the ledger.
        """
        if value is None:
            return value
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is not None and value.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "warehouse must belong to the caller's tenant.",
            )
        return value

    def validate_branch(self, value):
        """Branch (when supplied) must belong to the caller's tenant.

        The model column is nullable, so omitted/None is fine — but if the
        client *did* send a branch id, we must not silently accept a
        foreign-tenant branch and pollute the ledger.
        """
        if value is None:
            return value
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is not None and value.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "branch must belong to the caller's tenant.",
            )
        return value

    def create(self, validated_data):
        """Route the POST through the running-quantity service.

        Movement-type routing (mirrors and extends the legacy
        `OUTFLOW_TYPES` rule so the API stays backward compatible):

            PURCHASE_IN / RECEIVE_IN / RETURN_IN  → record_stock_in
            SALE_OUT                              → record_stock_out
            ADJUSTMENT, qty >= 0                  → record_stock_in
            ADJUSTMENT, qty <  0                  → record_stock_out (abs)

        The legacy serializer accepted a signed qty for ADJUSTMENT and
        let `Product.stock` go up or down accordingly; we preserve that
        signal here by inspecting the sign before calling the service.

        Any service-layer rule violation (cross-tenant branch, zero qty
        sneaking past, …) surfaces as a 400 — wrapped here so DRF
        renders it consistently with other validation errors instead of
        leaking the bare exception.
        """
        # Import locally to avoid circular import (services -> models).
        from pos.services import stock_movements as svc

        movement_type = validated_data['movement_type']
        signed_qty    = validated_data['qty']
        magnitude     = abs(signed_qty)
        product       = validated_data['product']
        branch        = validated_data.get('branch')
        warehouse     = validated_data.get('warehouse')
        note          = validated_data.get('note', '') or ''
        sale          = validated_data.get('sale')
        source_document_type = validated_data.get('source_document_type', '') or ''
        source_document_id   = validated_data.get('source_document_id')

        # Actor: prefer the value the client supplied (admin / import
        # path); otherwise fall back to the authenticated user.
        request = self.context.get('request')
        actor_user = (
            validated_data.get('actor_user')
            or getattr(request, 'user', None)
        )

        # Route: which service handles this movement_type?
        if movement_type == StockMovement.MovementType.SALE_OUT:
            recorder = svc.record_stock_out
        elif movement_type == StockMovement.MovementType.ADJUSTMENT:
            # Signed-qty contract: negative qty → decrease stock.
            recorder = svc.record_stock_out if signed_qty < 0 else svc.record_stock_in
        else:
            # PURCHASE_IN / RECEIVE_IN / RETURN_IN
            recorder = svc.record_stock_in

        try:
            movement = recorder(
                product=product,
                quantity=magnitude,
                movement_type=movement_type,
                branch=branch,
                warehouse=warehouse,
                source_document_type=source_document_type,
                source_document_id=source_document_id,
                actor_user=actor_user,
                note=note,
            )
        except svc.StockMovementError as exc:
            raise serializers.ValidationError({'detail': str(exc)})

        # Legacy `sale` FK isn't part of the service signature — attach
        # it after the service has done the heavy lifting so existing
        # callers (if any) that link a movement to a Sale still work.
        if sale is not None:
            movement.sale = sale
            movement.save(update_fields=['sale', 'updated_at'])

        return movement


class StockAdjustmentSerializer(serializers.Serializer):
    product    = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    actual_qty = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal('0'))
    reason     = serializers.CharField(max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and getattr(request.user, 'tenant', None):
            self.fields['product'].queryset = Product.objects.filter(tenant=request.user.tenant)


# ── Dynamic Warehouses (Phase 1.5 foundation) ─────────────────────────────────

class WarehouseSerializer(serializers.ModelSerializer):
    warehouse_type_display = serializers.CharField(
        source='get_warehouse_type_display', read_only=True,
    )

    class Meta:
        model  = Warehouse
        fields = [
            'id', 'code', 'name', 'warehouse_type', 'warehouse_type_display',
            'description', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'warehouse_type_display', 'created_at', 'updated_at']

    def validate_code(self, value):
        """`code` is unique per tenant — friendly 400 backing the DB constraint."""
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is None:
            return value
        qs = Warehouse.objects.filter(tenant=tenant, code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'A warehouse with this code already exists for this tenant.',
            )
        return value


class BranchWarehouseSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model  = BranchWarehouse
        fields = [
            'id', 'branch', 'warehouse', 'role', 'role_display',
            'is_default', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'role_display', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is not None:
            self.fields['branch'].queryset = Branch.objects.filter(tenant=tenant)
            self.fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)

    def validate(self, attrs):
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)

        # Merge incoming data over the existing instance so PATCH validates
        # against the would-be final row, not just the supplied fields.
        branch     = attrs.get('branch',     getattr(self.instance, 'branch', None))
        warehouse  = attrs.get('warehouse',  getattr(self.instance, 'warehouse', None))
        role       = attrs.get('role',       getattr(self.instance, 'role', None))
        is_default = attrs.get('is_default', getattr(self.instance, 'is_default', False))
        is_active  = attrs.get('is_active',  getattr(self.instance, 'is_active', True))

        # Cross-tenant guard: branch & warehouse must be in the caller's tenant
        # and must share the same tenant as each other.
        if tenant is not None:
            if branch is not None and branch.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {'branch': "branch must belong to the caller's tenant."})
            if warehouse is not None and warehouse.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {'warehouse': "warehouse must belong to the caller's tenant."})
        if (branch is not None and warehouse is not None
                and branch.tenant_id != warehouse.tenant_id):
            raise serializers.ValidationError(
                'branch and warehouse must belong to the same tenant.')

        # Friendly pre-checks mirroring the DB partial-unique constraints.
        if is_active:
            dup = BranchWarehouse.objects.filter(
                tenant=tenant, branch=branch, warehouse=warehouse,
                role=role, is_active=True,
            )
            if self.instance is not None:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError(
                    'An active link for this branch, warehouse, and role already exists.')

            if is_default:
                clash = BranchWarehouse.objects.filter(
                    branch=branch, role=role, is_active=True, is_default=True,
                )
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError(
                        'This branch already has a default warehouse for this role.')
        return attrs


# ── Sale serializers ──────────────────────────────────────────────────────────

class SaleItemSerializer(serializers.ModelSerializer):
    """
    Client sends: product (id), qty, price_each.
    Server fills:  product_name, barcode, line_total automatically.
    """

    class Meta:
        model  = SaleItem
        fields = ['id', 'product', 'product_name', 'barcode', 'qty', 'price_each', 'line_total']
        read_only_fields = ['id', 'product_name', 'barcode', 'line_total']


class SaleSerializer(serializers.ModelSerializer):
    """
    POST body (client sends):
        items          – list of {product, qty, price_each}
        method         – 'cash' | 'card' | 'wallet'
        paid           – amount tendered
        discount_type  – 'percent' | 'fixed' | null (optional)
        discount_value – numeric amount (optional, default 0)
        offline        – bool (optional, default False)

    Server auto-fills:
        cashier, branch, terminal   ← from JWT user
        subtotal, tax_amount, total ← computed from items + discount
        change                      ← paid - total
        sale_uuid                   ← auto-generated UUID

    Oversell policy (per FLOW.md):
        Selling beyond stock is ALLOWED.
        A warning is returned in the response: warnings[].
        Stock goes negative; StockMovement is flagged.
    """

    items         = SaleItemSerializer(many=True)
    cashier_name  = serializers.SerializerMethodField()
    branch_name   = serializers.SerializerMethodField()
    terminal_name = serializers.SerializerMethodField()
    warnings      = serializers.SerializerMethodField()
    # Write-only alias so clients can send either `paid` or `amount_paid`
    # (المدفوع). Both feed the same Payment.amount_paid column.
    amount_paid   = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True, required=False,
    )

    class Meta:
        model  = Sale
        fields = [
            'id', 'sale_uuid',
            'cashier', 'cashier_name',
            'branch', 'branch_name',
            'terminal', 'terminal_name',
            'subtotal', 'tax_amount', 'total',
            'discount_type', 'discount_value',
            'method', 'paid', 'amount_paid', 'change',
            'status', 'offline', 'receipt_printed',
            'created_at', 'warnings',
            'items',
        ]
        read_only_fields = [
            'id', 'sale_uuid',
            'cashier', 'branch', 'terminal',
            'subtotal', 'tax_amount', 'total', 'change',
            'created_at',
        ]

    def get_cashier_name(self, obj):
        if obj.cashier:
            return obj.cashier.get_full_name() or obj.cashier.username
        return ''

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else ''

    def get_terminal_name(self, obj):
        return obj.terminal.name if obj.terminal else ''

    def get_warnings(self, obj):
        return getattr(obj, '_warnings', [])

    # ── Validation ─────────────────────────────────────────────────────────────

    def validate(self, data):
        items = data.get('items', [])
        if not items:
            raise serializers.ValidationError({'items': 'At least one item is required.'})

        errors = {}
        for i, item in enumerate(items):
            qty        = item.get('qty',        Decimal('0'))
            price_each = item.get('price_each', Decimal('0'))
            product    = item.get('product')
            key        = f'items[{i}]'

            if qty <= 0:
                errors[f'{key}.qty'] = 'Must be greater than 0.'
            if price_each <= 0:
                errors[f'{key}.price_each'] = 'Must be greater than 0.'
            if product and product.unit == Product.Unit.PIECE and qty != qty.to_integral_value():
                errors[f'{key}.qty'] = 'Qty must be a whole number for piece-based products.'
            # Oversell is intentionally allowed — warning returned in response

        discount_type  = data.get('discount_type') or ''
        discount_value = data.get('discount_value', Decimal('0'))
        if discount_value < 0:
            errors['discount_value'] = 'Discount value cannot be negative.'
        if discount_type == Sale.DiscountType.PERCENT and discount_value > 100:
            errors['discount_value'] = 'Percent discount cannot exceed 100%.'

        if errors:
            raise serializers.ValidationError(errors)

        return data

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(self, validated_data):
        items_data = validated_data.pop('items')

        # `amount_paid` is a write-only alias for `paid` — pop it before it
        # reaches Sale.objects.create() (which doesn't have that column).
        amount_paid_alias = validated_data.pop('amount_paid', None)
        if amount_paid_alias is not None and validated_data.get('paid') in (None, Decimal('0')):
            validated_data['paid'] = amount_paid_alias

        subtotal   = sum(item['qty'] * item['price_each'] for item in items_data)
        tax_amount = sum(
            item['qty'] * item['price_each'] * (
                item['product'].tax_rate if item.get('product') else Decimal('0')
            )
            for item in items_data
        )

        discount_type  = validated_data.get('discount_type') or ''
        discount_value = validated_data.get('discount_value', Decimal('0'))

        if discount_type == Sale.DiscountType.PERCENT:
            discount_amount = subtotal * discount_value / Decimal('100')
        elif discount_type == Sale.DiscountType.FIXED:
            discount_amount = discount_value
        else:
            discount_amount = Decimal('0')

        total = subtotal + tax_amount - discount_amount
        paid  = validated_data.get('paid', Decimal('0'))

        if paid < total:
            raise serializers.ValidationError({
                'paid': (
                    f'Insufficient payment. '
                    f'Total is {total:.2f}, received {float(paid):.2f}.'
                )
            })

        change = paid - total
        method = validated_data.get('method', Sale.Method.CASH)
        # Fast-indexed mirror for reporting (per Sale model docstring).
        validated_data['payment_method_hint'] = method

        with transaction.atomic():
            sale = Sale.objects.create(
                subtotal   = round(subtotal,   2),
                tax_amount = round(tax_amount, 2),
                total      = round(total,      2),
                change     = round(change,     2),
                **validated_data,
            )

            for item_data in items_data:
                product = item_data.get('product')
                item_data['product_name'] = product.name        if product else ''
                item_data['barcode']      = product.barcode or '' if product else ''
                item_data['line_total']   = item_data['qty'] * item_data['price_each']
                SaleItem.objects.create(sale=sale, **item_data)

            # Payment ledger — separate row so reporting queries don't have
            # to JOIN cashier-tendered / change-given off the Sale table.
            Payment.objects.create(
                sale         = sale,
                method       = method,
                status       = Payment.Status.SUCCESS,
                amount       = sale.total,
                amount_paid  = paid,
                change       = sale.change,
                processed_at = timezone.now(),
            )

            if sale.status == Sale.Status.COMPLETED:
                self._apply_stock(sale)

        return sale

    # ── Stock helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _apply_stock(sale: Sale) -> None:
        """Deduct each line's qty from Product.stock under a row lock.

        Oversells are allowed (per FLOW.md) and produce a warning, but the
        actual decrement still goes through `Product.deduct_stock(...,
        allow_oversell=True)` so two concurrent checkouts of the last unit
        can't both succeed without one of them being flagged.
        """
        warnings = []
        with transaction.atomic():
            for item in sale.items.select_related('product').all():
                if not item.product:
                    continue

                product   = item.product
                qty_delta = item.qty
                note      = f'Sale #{sale.pk}'

                # Lock + read in one round-trip so the oversell decision uses
                # the authoritative current value, not a stale select.
                try:
                    product.deduct_stock(qty_delta)
                except InsufficientStockError as exc:
                    msg = (
                        f'Only {exc.available} in stock. '
                        f'Sold {exc.requested} of "{product.name}".'
                    )
                    logger.warning(
                        'OVERSOLD: product "%s" (id=%s), requested=%s, had=%s',
                        product.name, product.pk, exc.requested, exc.available,
                    )
                    warnings.append(msg)
                    note = f'Sale #{sale.pk} — oversold'
                    # Re-attempt allowing the negative balance so the audit
                    # trail (StockMovement) still records the outflow.
                    product.deduct_stock(qty_delta, allow_oversell=True)

                StockMovement.objects.create(
                    tenant=sale.tenant,
                    product=product,
                    qty=-qty_delta,
                    movement_type=StockMovement.MovementType.SALE_OUT,
                    sale=sale,
                    note=note,
                )

                if product.stock < product.reorder:
                    logger.warning(
                        'LOW STOCK: "%s" (id=%s) stock=%s below reorder=%s',
                        product.name, product.pk, product.stock, product.reorder,
                    )

        sale._warnings = warnings


class SaleListSerializer(serializers.ModelSerializer):
    cashier_name  = serializers.SerializerMethodField()
    branch_name   = serializers.SerializerMethodField()
    terminal_name = serializers.SerializerMethodField()
    item_count    = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model  = Sale
        fields = [
            'id', 'sale_uuid',
            'cashier', 'cashier_name',
            'branch', 'branch_name',
            'terminal', 'terminal_name',
            'subtotal', 'tax_amount', 'total',
            'discount_type', 'discount_value',
            'method', 'paid', 'status', 'offline',
            'receipt_printed', 'created_at', 'item_count',
        ]

    def get_cashier_name(self, obj):
        if obj.cashier:
            return obj.cashier.get_full_name() or obj.cashier.username
        return ''

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else ''

    def get_terminal_name(self, obj):
        return obj.terminal.name if obj.terminal else ''


# ── Receipt / Invoice ─────────────────────────────────────────────────────────

class ReceiptSerializer(serializers.Serializer):
    """Structured layout for the printed bill — see Hyper Fekra Quesna design.

    Three sections:
      * `auto`   — fields the system fills (date, terminal, serial, cashier,
                   line columns, totals block). Cannot be configured.
      * `config` — text blocks pulled live from the Tenant row
                   (`receipt_header`, `receipt_footer`, currency, VAT, etc.).
                   Editing these in the business dashboard updates every
                   future receipt with no code change.
      * `lines`  — the [الصنف | الكمية | السعر | القيمة] matrix.

    Inputs: a fully-saved `Sale` instance (with its `payment` related row).
    """

    def to_representation(self, sale):
        tenant   = sale.tenant
        branch   = sale.branch
        terminal = sale.terminal
        cashier  = sale.cashier
        payment  = getattr(sale, 'payment', None)

        # Prefer Payment.amount_paid / change — that's the authoritative
        # ledger; fall back to Sale columns for legacy rows without a Payment.
        amount_paid = (
            payment.amount_paid
            if payment and payment.amount_paid is not None
            else sale.paid
        )
        change_due = (
            payment.change
            if payment and payment.change is not None
            else sale.change
        )

        discount_amount = sale.subtotal + sale.tax_amount - sale.total
        local_dt = timezone.localtime(sale.created_at)
        lines = [
            {
                'item':       item.product_name,
                'qty':        str(item.qty),
                'price':      str(item.price_each),
                'line_total': str(item.line_total),
            }
            for item in sale.items.all()
        ]

        return {
            'auto': {
                'date':            local_dt.strftime('%Y-%m-%d'),
                'time':            local_dt.strftime('%H:%M:%S'),
                'terminal':        terminal.name if terminal else '',
                'terminal_serial': terminal.serial if terminal else '',
                'branch':          branch.name if branch else '',
                'serial':          sale.pk,
                'sale_uuid':       str(sale.sale_uuid),
                'cashier':         (cashier.get_full_name() or cashier.username) if cashier else '',
                'columns':         ['الصنف', 'الكمية', 'السعر', 'القيمة'],
            },
            'config': {
                'business_name':  tenant.name if tenant else '',
                'receipt_header': getattr(tenant, 'receipt_header', '') if tenant else '',
                'receipt_footer': getattr(tenant, 'receipt_footer', '') if tenant else '',
                'address':        (getattr(tenant, 'address', '') or '') if tenant else '',
                'phone':          (getattr(tenant, 'phone', '')   or '') if tenant else '',
                'vat_number':     (getattr(tenant, 'vat_number', '') or '') if tenant else '',
                'currency':       getattr(tenant, 'currency', 'EGP') if tenant else 'EGP',
                'show_tax':       getattr(tenant, 'show_tax_on_receipt', True) if tenant else True,
                'logo':           (tenant.logo.url if tenant and tenant.logo else None),
            },
            'lines': lines,
            'totals': {
                'subtotal':      str(sale.subtotal),
                'tax':           str(sale.tax_amount),
                'discount':      str(
                    discount_amount.quantize(Decimal('0.01'))
                    if isinstance(discount_amount, Decimal) else discount_amount
                ),
                'discount_type': sale.discount_type or '',
                'total_due':     str(sale.total),
                'item_count':    sale.items.count(),
                'amount_paid':   str(amount_paid),
                'change':        str(change_due),
                'method':        sale.method,
            },
        }
