import django_filters
from .models import (
    BranchWarehouse, InventoryCategory, InventoryCostMovement, Product, Sale,
    SalesCategory, StockMovement, Unit, UnitGroup, Warehouse, WarehouseStock,
)


class SalesCategoryFilter(django_filters.FilterSet):
    """Filters for the hierarchical sales-category tree (Sprint 2 Batch 2)."""

    active = django_filters.BooleanFilter(field_name='is_active')
    # `root=true` → only top-level nodes (parent IS NULL).
    root   = django_filters.BooleanFilter(field_name='parent', lookup_expr='isnull')

    class Meta:
        model  = SalesCategory
        fields = ['parent', 'is_active']


class InventoryCategoryFilter(django_filters.FilterSet):
    """Filters for the hierarchical inventory-category tree (Sprint 2 Batch 2)."""

    active = django_filters.BooleanFilter(field_name='is_active')
    root   = django_filters.BooleanFilter(field_name='parent', lookup_expr='isnull')

    class Meta:
        model  = InventoryCategory
        fields = ['parent', 'is_active']


class UnitGroupFilter(django_filters.FilterSet):
    """Filters for the tenant unit-group catalog (Sprint 2 Batch 1)."""

    # `active` is the contract-facing alias for the `is_active` column.
    active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model  = UnitGroup
        fields = ['is_active']


class UnitFilter(django_filters.FilterSet):
    """Filters for the tenant unit catalog (Sprint 2 Batch 1)."""

    active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model  = Unit
        fields = ['unit_group', 'allow_decimal', 'is_active']


class ProductFilter(django_filters.FilterSet):
    category     = django_filters.CharFilter(field_name='category__name', lookup_expr='iexact')
    low_stock    = django_filters.BooleanFilter(method='filter_low_stock')
    out_of_stock = django_filters.BooleanFilter(method='filter_out_of_stock')
    min_price    = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price    = django_filters.NumberFilter(field_name='price', lookup_expr='lte')

    class Meta:
        model  = Product
        # `plu` is exact-match: the POS scanner queries `?plu=00041` to resolve
        # a weight-barcode (EAN-13 `21`-prefixed) back to its catalog product.
        # `show_on_pos` is opt-in (Sprint 2 Batch 5a): omitted entirely by
        # default, so existing admin screens keep seeing every product
        # unchanged; the POS catalog view passes `?show_on_pos=true` explicitly.
        fields = ['category', 'active', 'weighted', 'plu', 'show_on_pos']

    def filter_low_stock(self, queryset, name, value):
        if value:
            from django.db.models import F
            return queryset.filter(stock__gt=0, stock__lt=F('reorder'))
        return queryset

    def filter_out_of_stock(self, queryset, name, value):
        if value:
            return queryset.filter(stock=0)
        return queryset


class StockMovementFilter(django_filters.FilterSet):
    """Filters for the global inventory ledger."""

    # Frontend-friendly YYYY-MM-DD range. Both ends inclusive.
    start_date    = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    end_date      = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    product_id    = django_filters.NumberFilter(field_name='product__id')
    movement_type = django_filters.CharFilter(field_name='movement_type')

    class Meta:
        model  = StockMovement
        fields = ['movement_type', 'product_id', 'warehouse']


class InventoryCostMovementFilter(django_filters.FilterSet):
    """Filters for a product's AVCO audit trail (Sprint 4 Batch 3).

    Mirrors `StockMovementFilter`'s `start_date`/`end_date` range shape
    exactly. Cost data has no branch/warehouse dimension (D-09 keeps
    `InventoryCost` tenant-wide), so no branch/warehouse filter exists
    here — there is nothing to filter by."""

    start_date            = django_filters.DateFilter(field_name='occurred_at', lookup_expr='date__gte')
    end_date              = django_filters.DateFilter(field_name='occurred_at', lookup_expr='date__lte')
    source_document_type  = django_filters.CharFilter(field_name='source_document_type')

    class Meta:
        model  = InventoryCostMovement
        fields = ['source_document_type']


class WarehouseFilter(django_filters.FilterSet):
    """Filters for the tenant warehouse catalog."""

    # `active` is the contract-facing alias for the `is_active` column.
    active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model  = Warehouse
        fields = ['warehouse_type', 'is_active']


class BranchWarehouseFilter(django_filters.FilterSet):
    """Filters for branch↔warehouse links.

    The prompt's `is_default_sales/purchase/returns/damage` filters collapse
    into `role` + `is_default` under the role-based model.
    """

    active         = django_filters.BooleanFilter(field_name='is_active')
    warehouse_type = django_filters.CharFilter(field_name='warehouse__warehouse_type')

    class Meta:
        model  = BranchWarehouse
        fields = ['branch', 'warehouse', 'role', 'is_default', 'is_active']


class WarehouseStockFilter(django_filters.FilterSet):
    """Filters for cached per-warehouse stock balances (read-only resource)."""

    low_stock = django_filters.BooleanFilter(method='filter_low_stock')
    has_stock = django_filters.BooleanFilter(method='filter_has_stock')

    class Meta:
        model  = WarehouseStock
        fields = ['warehouse', 'product']

    def filter_low_stock(self, queryset, name, value):
        if value:
            from django.db.models import F
            return queryset.filter(quantity__lte=F('product__reorder'))
        return queryset

    def filter_has_stock(self, queryset, name, value):
        # Non-zero balance (positive or negative), i.e. the product has moved
        # through this warehouse.
        if value:
            return queryset.exclude(quantity=0)
        return queryset


class SaleFilter(django_filters.FilterSet):
    date_from  = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to    = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    # Frontend-friendly YYYY-MM-DD filters. `end_date` is inclusive — anything
    # on that calendar day counts, regardless of time of day.
    start_date = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    end_date   = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    cashier    = django_filters.NumberFilter(field_name='cashier__id')
    branch     = django_filters.CharFilter(field_name='branch__name', lookup_expr='icontains')

    class Meta:
        model  = Sale
        fields = ['method', 'status', 'offline']
