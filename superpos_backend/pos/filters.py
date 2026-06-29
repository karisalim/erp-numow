import django_filters
from .models import BranchWarehouse, Product, Sale, StockMovement, Warehouse


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
        fields = ['category', 'active', 'weighted', 'plu']

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
