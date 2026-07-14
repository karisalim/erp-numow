import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from accounts.models import (
    Branch, Customer, FinancialAccount, PaymentMethod, Supplier,
)
from .models import (
    BranchWarehouse, Category, InsufficientStockError, InventoryBatch,
    InventoryCategory, Payment, Product, ProductBarcodeUnit, ProductUnit,
    PurchaseInvoice, PurchaseInvoiceLine, Sale, SaleItem, SalesCategory,
    StockMovement, Unit, UnitGroup, Warehouse, WarehouseStock,
)

logger = logging.getLogger(__name__)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ['id', 'name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductSerializer(serializers.ModelSerializer):
    """Catalog product.

    Sprint 2 Batch 3 additions are strictly additive — every legacy field
    keeps its exact name, shape, and behavior (FE compatibility):
      * `product_type` + read-only `behavior` flags calculated from the
        centralized matrix (services/product_types.py) — never stored
      * `sales_category` / `inventory_category` links into the Batch 2 trees
        (tenant-validated; the legacy flat `category` stays untouched)
      * `show_on_pos` / `is_discountable` classification booleans
      * reverse barcode-collision guard: `Product.barcode` may not collide
        with any pack barcode in `ProductBarcodeUnit` (the forward direction
        already lives in ProductBarcodeUnitSerializer) so scan resolution
        stays unambiguous when Batch 5 wires the precedence
    """

    category_name = serializers.CharField(source='category.name', read_only=True)
    margin        = serializers.FloatField(read_only=True)
    unit_display  = serializers.CharField(source='get_unit_display', read_only=True)

    product_type_display    = serializers.CharField(
        source='get_product_type_display', read_only=True)
    sales_category_name     = serializers.CharField(
        source='sales_category.name', read_only=True)
    inventory_category_name = serializers.CharField(
        source='inventory_category.name', read_only=True)
    behavior                = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id', 'barcode', 'sku', 'name', 'category', 'category_name',
            'price', 'cost', 'tax_rate', 'stock', 'reorder', 'color',
            'weighted', 'unit', 'unit_display', 'pack_qty', 'plu', 'active',
            'margin',
            'product_type', 'product_type_display', 'behavior',
            'sales_category', 'sales_category_name',
            'inventory_category', 'inventory_category_name',
            'show_on_pos', 'is_discountable',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'product_type_display', 'behavior',
            'sales_category_name', 'inventory_category_name',
            'created_at', 'updated_at',
        ]

    def _tenant(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'tenant', None)

    def get_behavior(self, obj):
        from pos.services.product_types import behavior_flags
        return behavior_flags(obj.product_type)

    def _validate_tree_category(self, value, tree_label):
        """Shared rule for both tree FKs: caller's tenant + active."""
        if value is None:
            return value
        tenant = self._tenant()
        if tenant is not None and value.tenant_id != tenant.id:
            raise serializers.ValidationError(
                f"{tree_label} must belong to the caller's tenant.",
            )
        if not value.is_active:
            raise serializers.ValidationError(
                f'{tree_label} is inactive; pick an active category.',
            )
        return value

    def validate_sales_category(self, value):
        return self._validate_tree_category(value, 'sales_category')

    def validate_inventory_category(self, value):
        return self._validate_tree_category(value, 'inventory_category')

    def validate(self, attrs):
        from pos.services import units as units_svc
        from pos.services.product_types import get_behavior

        tenant = self._tenant() or getattr(self.instance, 'tenant', None)

        # Reverse barcode collision (closes the one-directional gap from
        # Batch 1): a legacy product barcode that also lives in the pack
        # namespace would make future scan precedence ambiguous. Only checked
        # when the barcode actually CHANGES — a full PUT resending an
        # unchanged (already-colliding) barcode must not break legacy edits;
        # the seed command's audit pass reports those for the operator.
        barcode = attrs.get('barcode')
        barcode_changes = (
            'barcode' in attrs
            and (self.instance is None or barcode != self.instance.barcode)
        )
        if tenant is not None and barcode and barcode_changes:
            if ProductBarcodeUnit.objects.filter(
                    tenant=tenant, barcode=barcode).exists():
                raise serializers.ValidationError({
                    'barcode': (
                        'This barcode is already assigned to a product unit '
                        '(pack barcode); pick a distinct product barcode.'
                    ),
                })

        # Type-change guard (same philosophy as the base-unit immutability
        # rule): once stock history exists in the ledger, the product cannot
        # be reclassified to a type that stops tracking inventory — the
        # movements would be orphaned from any interpretable balance.
        new_type = attrs.get('product_type')
        if (
            self.instance is not None
            and new_type
            and new_type != self.instance.product_type
            and get_behavior(self.instance.product_type).track_inventory
            and not get_behavior(new_type).track_inventory
            and units_svc.product_has_stock_history(self.instance)
        ):
            raise serializers.ValidationError({
                'product_type': (
                    'This product has stock movement history; it cannot be '
                    'reclassified to a non-inventory type '
                    f'({new_type!r}). Deactivate it and create a new product '
                    'instead.'
                ),
            })
        return attrs

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = self._tenant()
        if tenant is not None:
            self.fields['sales_category'].queryset = \
                SalesCategory.objects.filter(tenant=tenant)
            self.fields['inventory_category'].queryset = \
                InventoryCategory.objects.filter(tenant=tenant)


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


# ── Category Trees (Sprint 2 Batch 2 — MASTER_DATA_CONTRACT §3) ───────────────


class _CategoryTreeSerializerMixin:
    """Shared parent-validation rules for both hierarchical category trees.

    Enforced here — NOT only via DB constraints (a cycle is inexpressible
    declaratively):
      * parent must belong to the caller's tenant
      * parent must be active (inactive nodes accept no NEW assignments)
      * a category cannot be its own parent
      * a category cannot become a child of one of its own descendants
        (walk-up ancestor check, unlimited depth)
      * sibling / root name uniqueness gets a friendly 400 backing the DB
        constraints
    """

    def _tenant(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'tenant', None)

    def validate_parent(self, parent):
        if parent is None:
            return parent
        tenant = self._tenant()
        if tenant is not None and parent.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "parent must belong to the caller's tenant.",
            )
        if not parent.is_active:
            raise serializers.ValidationError(
                'parent is inactive; inactive categories cannot take new children.',
            )
        if self.instance is not None:
            if parent.pk == self.instance.pk:
                raise serializers.ValidationError(
                    'A category cannot be its own parent.',
                )
            # Cycle guard: if `instance` appears among the proposed parent's
            # ancestors, attaching it would close a loop (C cannot become the
            # parent of A when A → B → C). `seen` stops a walk over already-
            # corrupt data from spinning forever.
            node, seen = parent.parent, {parent.pk}
            while node is not None:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        'Circular hierarchy: the chosen parent is a '
                        'descendant of this category.',
                    )
                if node.pk in seen:
                    break
                seen.add(node.pk)
                node = node.parent
        return parent

    def validate(self, attrs):
        tenant = self._tenant()
        model = self.Meta.model
        name = attrs.get('name', getattr(self.instance, 'name', None))
        # PATCH may omit `parent`; distinguish "not sent" from "set to null".
        if 'parent' in attrs:
            parent = attrs['parent']
        else:
            parent = getattr(self.instance, 'parent', None)

        if tenant is not None and name:
            qs = model.objects.filter(tenant=tenant, parent=parent, name=name)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                where = 'at the root level' if parent is None else 'under this parent'
                raise serializers.ValidationError({
                    'name': f'A category named {name!r} already exists {where}.',
                })
        return attrs


class SalesCategorySerializer(_CategoryTreeSerializerMixin, serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model  = SalesCategory
        fields = [
            'id', 'name', 'parent', 'parent_name', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'parent_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = self._tenant()
        if tenant is not None:
            self.fields['parent'].queryset = SalesCategory.objects.filter(tenant=tenant)


class InventoryCategorySerializer(_CategoryTreeSerializerMixin, serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model  = InventoryCategory
        fields = [
            'id', 'name', 'parent', 'parent_name', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'parent_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tenant = self._tenant()
        if tenant is not None:
            self.fields['parent'].queryset = InventoryCategory.objects.filter(tenant=tenant)


# ── Dynamic Units (Sprint 2 Batch 1 — MASTER_DATA_CONTRACT §2) ────────────────
# Tenant scoping convention mirrors BranchPaymentMethodSerializer: `tenant` is
# injected by the view from the auth context, every FK is validated to live in
# the caller's tenant, and DB constraints get friendly 400 twins here.


class UnitGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UnitGroup
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is None:
            return value
        qs = UnitGroup.objects.filter(tenant=tenant, name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'A unit group with this name already exists for this tenant.',
            )
        return value


class UnitSerializer(serializers.ModelSerializer):
    unit_group_name = serializers.CharField(source='unit_group.name', read_only=True)

    class Meta:
        model  = Unit
        fields = [
            'id', 'unit_group', 'unit_group_name', 'name', 'symbol',
            'factor_to_base', 'allow_decimal', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'unit_group_name', 'created_at', 'updated_at']

    def _tenant(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'tenant', None)

    def validate_unit_group(self, group):
        tenant = self._tenant()
        if tenant is not None and group is not None and group.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "unit_group must belong to the caller's tenant.",
            )
        return group

    def validate_factor_to_base(self, value):
        if value <= 0:
            raise serializers.ValidationError('factor_to_base must be > 0.')
        return value

    def validate(self, attrs):
        tenant = self._tenant()
        group = attrs.get('unit_group') or getattr(self.instance, 'unit_group', None)
        name  = attrs.get('name') or getattr(self.instance, 'name', None)
        if tenant is not None and group is not None and name:
            qs = Unit.objects.filter(tenant=tenant, unit_group=group, name=name)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'name': 'A unit with this name already exists in this group.',
                })
        return attrs


class ProductUnitSerializer(serializers.ModelSerializer):
    """Per-product conversion mapping (nested under /products/{pk}/units/).

    `product` comes from the URL (view passes it via `save(product=..)`),
    never from the body. Rules enforced here (friendly 400s backing the DB
    constraints):
      * unit must be tenant-scoped and active
      * one mapping per (product, unit)
      * at most one base mapping per product; base conversion is exactly 1
      * the base mapping is immutable once the product has stock history
        (pos.services.units.assert_base_mapping_mutable)
    """

    unit_name   = serializers.CharField(source='unit.name',   read_only=True)
    unit_symbol = serializers.CharField(source='unit.symbol', read_only=True)
    allow_decimal = serializers.BooleanField(source='unit.allow_decimal', read_only=True)

    class Meta:
        model  = ProductUnit
        fields = [
            'id', 'unit', 'unit_name', 'unit_symbol', 'allow_decimal',
            'conversion_to_base', 'is_base',
            'is_sale_unit', 'is_purchase_unit', 'is_recipe_unit',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'unit_name', 'unit_symbol', 'allow_decimal',
            'created_at', 'updated_at',
        ]

    def _tenant(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'tenant', None)

    def validate_unit(self, unit):
        tenant = self._tenant()
        if tenant is not None and unit is not None and unit.tenant_id != tenant.id:
            raise serializers.ValidationError(
                "unit must belong to the caller's tenant.",
            )
        if unit is not None and not unit.is_active:
            raise serializers.ValidationError('unit is inactive.')
        return unit

    def validate_conversion_to_base(self, value):
        if value <= 0:
            raise serializers.ValidationError('conversion_to_base must be > 0.')
        return value

    def validate(self, attrs):
        from pos.services import units as units_svc

        product = self.context.get('product') or getattr(self.instance, 'product', None)
        unit    = attrs.get('unit') or getattr(self.instance, 'unit', None)
        is_base = attrs.get('is_base', getattr(self.instance, 'is_base', False))
        conversion = attrs.get(
            'conversion_to_base',
            getattr(self.instance, 'conversion_to_base', Decimal('1')),
        )

        # One mapping per (product, unit).
        if product is not None and unit is not None:
            qs = ProductUnit.objects.filter(product=product, unit=unit)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'unit': 'This unit is already mapped for this product.',
                })

        if is_base:
            # Base mapping is the identity by definition.
            if conversion != Decimal('1'):
                raise serializers.ValidationError({
                    'conversion_to_base': 'The base mapping must have conversion_to_base = 1.',
                })
            # One base per product.
            if product is not None:
                clash = ProductUnit.objects.filter(product=product, is_base=True)
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError({
                        'is_base': 'This product already has a base unit mapping.',
                    })

        # Base immutability: once movements exist, the established base mapping
        # cannot be edited, demoted, or displaced (re-denomination = future
        # explicit document). Creating the FIRST base mapping stays allowed.
        touches_base = (
            (self.instance is not None and self.instance.is_base)  # editing the base row
            or is_base                                             # or promoting one
        )
        if product is not None and touches_base:
            changing = True
            if self.instance is not None and self.instance.is_base:
                # Editing the existing base row is harmless if nothing
                # denomination-relevant changes.
                changing = (
                    unit != self.instance.unit
                    or conversion != self.instance.conversion_to_base
                    or not is_base
                )
            elif self.instance is None and is_base:
                changing = True  # creating a base row
            try:
                if changing:
                    units_svc.assert_base_mapping_mutable(product)
            except units_svc.UnitConversionError as exc:
                # When creating the first base row there is no existing base,
                # so the guard passes; it only raises when a base already
                # exists AND history exists.
                raise serializers.ValidationError({
                    'is_base': str(exc),
                    'code': units_svc.UnitConversionError.code,
                })
        return attrs


class ProductBarcodeUnitSerializer(serializers.ModelSerializer):
    """Per-pack barcode (nested under /products/{pk}/barcodes/).

    `(tenant, barcode)` is DB-unique within this table; collisions against the
    legacy `Product.barcode` namespace are rejected here (no cross-table DB
    constraint is possible) so scan resolution stays unambiguous when Batch 3
    wires the precedence.
    """

    unit_name = serializers.CharField(source='product_unit.unit.name', read_only=True)
    conversion_to_base = serializers.DecimalField(
        source='product_unit.conversion_to_base',
        max_digits=16, decimal_places=6, read_only=True,
    )

    class Meta:
        model  = ProductBarcodeUnit
        fields = [
            'id', 'product_unit', 'unit_name', 'conversion_to_base',
            'barcode', 'is_default', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'unit_name', 'conversion_to_base', 'created_at', 'updated_at',
        ]

    def _tenant(self):
        request = self.context.get('request')
        return getattr(getattr(request, 'user', None), 'tenant', None)

    def validate(self, attrs):
        tenant  = self._tenant()
        product = self.context.get('product') or getattr(self.instance, 'product', None)
        product_unit = attrs.get('product_unit') or getattr(self.instance, 'product_unit', None)
        barcode = attrs.get('barcode') or getattr(self.instance, 'barcode', None)

        if product is not None and product_unit is not None \
                and product_unit.product_id != product.pk:
            raise serializers.ValidationError({
                'product_unit': 'product_unit must belong to this product.',
            })

        if tenant is not None and barcode:
            qs = ProductBarcodeUnit.objects.filter(tenant=tenant, barcode=barcode)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'barcode': 'This barcode is already assigned to a product unit.',
                })
            # Collision against the legacy per-product barcode namespace.
            if Product.objects.filter(tenant=tenant, barcode=barcode).exists():
                raise serializers.ValidationError({
                    'barcode': (
                        'This barcode already identifies a product '
                        '(legacy Product.barcode); pick a distinct pack barcode.'
                    ),
                })
        return attrs


class WarehouseStockSerializer(serializers.ModelSerializer):
    """Read-only cached per-(product, warehouse) balance (Phase 1.5 Slice J).

    Fully read-only: balances are maintained from stock movements via
    `pos.services.stock_movements.apply_warehouse_delta`, never written through
    the API.
    """

    product_name   = serializers.CharField(source='product.name', read_only=True)
    product_sku    = serializers.CharField(source='product.sku',  read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    warehouse_code = serializers.CharField(source='warehouse.code', read_only=True)

    class Meta:
        model  = WarehouseStock
        fields = [
            'id',
            'product', 'product_name', 'product_sku',
            'warehouse', 'warehouse_name', 'warehouse_code',
            'quantity', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


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


# ── Purchase Invoices (Phase 1.5 Slice H) ─────────────────────────────────────

class PurchaseInvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model  = PurchaseInvoiceLine
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'line_type',
            'qty', 'unit_cost', 'discount_amount', 'tax_amount',
            'line_total', 'notes',
        ]
        read_only_fields = ['id', 'product_name', 'line_total']

    def validate_qty(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError('qty must be > 0')
        return value

    def validate_line_type(self, value):
        if value and value != PurchaseInvoiceLine.LineType.STOCK_ITEM:
            raise serializers.ValidationError(
                "Only 'stock_item' lines are supported in this slice.")
        return value

    def validate(self, attrs):
        line_type = attrs.get('line_type') or PurchaseInvoiceLine.LineType.STOCK_ITEM
        if line_type == PurchaseInvoiceLine.LineType.STOCK_ITEM and attrs.get('product') is None:
            raise serializers.ValidationError(
                {'product': 'product is required for a stock_item line.'})
        for fld in ('unit_cost', 'discount_amount', 'tax_amount'):
            val = attrs.get(fld)
            if val is not None and val < 0:
                raise serializers.ValidationError({fld: f'{fld} must be >= 0'})
        return attrs


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    lines         = PurchaseInvoiceLineSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name   = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model  = PurchaseInvoice
        fields = [
            'id', 'branch', 'branch_name', 'supplier', 'supplier_name',
            'reference',
            'subtotal', 'discount_total', 'tax_total', 'total_amount',
            'paid_amount', 'credit_amount',
            'payment_method', 'source_account',
            'posting_status', 'payment_status', 'posted_at',
            'actor_user', 'notes', 'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'branch_name', 'supplier_name',
            'subtotal', 'discount_total', 'tax_total', 'total_amount',
            'credit_amount', 'posting_status', 'payment_status', 'posted_at',
            'actor_user', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is not None:
            self.fields['branch'].queryset         = Branch.objects.filter(tenant=tenant)
            self.fields['supplier'].queryset       = Supplier.objects.filter(tenant=tenant)
            self.fields['payment_method'].queryset = PaymentMethod.objects.filter(tenant=tenant)
            self.fields['source_account'].queryset = FinancialAccount.objects.filter(tenant=tenant)
            line_fields = self.fields['lines'].child.fields
            line_fields['product'].queryset   = Product.objects.filter(tenant=tenant)
            line_fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)

    def validate(self, attrs):
        paid = attrs.get('paid_amount') or Decimal('0')
        if paid < 0:
            raise serializers.ValidationError({'paid_amount': 'paid_amount must be >= 0'})
        if not attrs.get('lines'):
            raise serializers.ValidationError({'lines': 'at least one line is required'})
        return attrs

    def create(self, validated_data):
        # Local import to avoid any serializer ↔ service import cycle.
        from pos.services import purchase_invoices as svc

        request = self.context.get('request')
        tenant  = getattr(getattr(request, 'user', None), 'tenant', None)
        actor   = getattr(request, 'user', None)
        lines   = validated_data.pop('lines')
        try:
            invoice = svc.post_purchase_invoice(
                tenant=tenant,
                branch=validated_data['branch'],
                supplier=validated_data['supplier'],
                lines=lines,
                payment_method=validated_data.get('payment_method'),
                source_account=validated_data.get('source_account'),
                paid_amount=validated_data.get('paid_amount') or Decimal('0'),
                reference=validated_data.get('reference', '') or '',
                notes=validated_data.get('notes', '') or '',
                actor_user=actor,
            )
        except svc.PurchaseInvoiceError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        return invoice


# ── Sale serializers ──────────────────────────────────────────────────────────

class SaleItemSerializer(serializers.ModelSerializer):
    """
    Client sends: product (id), qty, price_each, optional warehouse.
    Server fills:  product_name, barcode, line_total, unit_cost automatically.
    """

    class Meta:
        model  = SaleItem
        fields = [
            'id', 'product', 'product_name', 'barcode',
            'qty', 'price_each', 'line_total', 'unit_cost', 'warehouse',
        ]
        read_only_fields = ['id', 'product_name', 'barcode', 'line_total', 'unit_cost']


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
            'customer',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is not None:
            self.fields['customer'].queryset = Customer.objects.filter(tenant=tenant)
            item_fields = self.fields['items'].child.fields
            item_fields['product'].queryset = Product.objects.filter(tenant=tenant)
            item_fields['warehouse'].queryset = Warehouse.objects.filter(tenant=tenant)

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

        # Credit sales settle into Customer AR, so a customer is mandatory.
        if data.get('method') == Sale.Method.CREDIT and not data.get('customer'):
            errors['customer'] = 'A customer is required for a credit sale.'

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

        total  = subtotal + tax_amount - discount_amount
        method = validated_data.get('method', Sale.Method.CASH)
        paid   = validated_data.get('paid', Decimal('0'))

        # Credit sales settle the full total into Customer AR — no cash is
        # tendered now, so the "paid >= total" rule and change don't apply.
        if method == Sale.Method.CREDIT:
            change = Decimal('0')
        else:
            if paid < total:
                raise serializers.ValidationError({
                    'paid': (
                        f'Insufficient payment. '
                        f'Total is {total:.2f}, received {float(paid):.2f}.'
                    )
                })
            change = paid - total

        # Fast-indexed mirror for reporting (per Sale model docstring).
        validated_data['payment_method_hint'] = method
        customer = validated_data.get('customer')

        # Ledger integration (Phase 1.5 Slice I) — resolve the branch's default
        # sales warehouse once. None when unconfigured → legacy behavior.
        from pos.services import sale_posting
        request = self.context.get('request')
        actor   = getattr(request, 'user', None)
        tenant  = validated_data.get('tenant') or getattr(actor, 'tenant', None)
        branch  = validated_data.get('branch')
        default_warehouse = sale_posting.resolve_sales_warehouse(tenant=tenant, branch=branch)

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
                # Cost snapshot for future COGS; explicit-or-default warehouse.
                item_data['unit_cost']    = product.cost if product else Decimal('0')
                if item_data.get('warehouse') is None:
                    item_data['warehouse'] = default_warehouse
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
                # Post the financial / AR effect. Runs in this atomic block so
                # any posting failure rolls back the whole sale.
                #
                # GA-2 strict routing: every completed cash/card/wallet sale
                # must resolve an active BranchPaymentMethod route. A missing /
                # inactive / misconfigured route — or an AR / account rule
                # violation — surfaces as a 400 and rolls the sale back. There
                # is no legacy best-effort skip anymore — see
                # sale_posting.post_sale_ledgers.
                #
                # Error shape (GA-8): keeps the legacy `payment` string key
                # (the frontend displays it) and adds stable machine-readable
                # `code` / `field` / `detail` keys.
                try:
                    sale_posting.post_sale_ledgers(
                        sale=sale, method=method, customer=customer, actor_user=actor,
                    )
                except (
                    sale_posting.SalePostingError,
                    sale_posting.ar.CustomerARError,
                    sale_posting.fa.AccountMovementError,
                ) as exc:
                    # Raised during save() — list-wrap the display message to
                    # match the standard {field: [messages]} error shape.
                    raise serializers.ValidationError({
                        'payment': [str(exc)],
                        'code': getattr(exc, 'code', 'sale_posting_error'),
                        'field': 'method',
                        'detail': str(exc),
                    })

        return sale

    # ── Stock helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _apply_stock(sale: Sale) -> None:
        """Deduct each line's qty from the global Product.stock under a row lock.

        Oversells are allowed (per FLOW.md) and produce a warning, but the
        actual decrement still goes through `Product.deduct_stock(...,
        allow_oversell=True)` so two concurrent checkouts of the last unit
        can't both succeed without one of them being flagged.

        Warehouse note: each movement records `item.warehouse` purely for
        traceability (which location the goods left). The authoritative on-hand
        quantity is still the single global `Product.stock` counter — there is
        no per-warehouse balance yet (deferred to a future slice). So the
        warehouse on the movement *labels* the outflow; it does not *scope* it.
        """
        from pos.services import stock_movements as stock_svc

        warnings = []
        with transaction.atomic():
            for item in sale.items.select_related('product', 'warehouse').all():
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
                    branch=sale.branch,
                    warehouse=item.warehouse,
                    qty=-qty_delta,
                    movement_type=StockMovement.MovementType.SALE_OUT,
                    sale=sale,
                    source_document_type='sale',
                    source_document_id=sale.id,
                    actor_user=sale.cashier,
                    note=note,
                )

                # Mirror the deduction into the cached per-warehouse balance.
                # The sale path deducts via Product.deduct_stock (not the
                # stock-movements service), so it calls the same helper here.
                # No-op when item.warehouse is None (unconfigured tenant).
                stock_svc.apply_warehouse_delta(
                    product=product, warehouse=item.warehouse, delta=-qty_delta,
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
