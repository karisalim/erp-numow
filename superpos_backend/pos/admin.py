from django.contrib import admin
from .models import Category, InventoryBatch, Product, Sale, SaleItem, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'tenant']
    list_filter   = ['tenant']
    search_fields = ['name', 'tenant__name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ['name', 'sku', 'barcode', 'tenant', 'category', 'price', 'stock', 'active']
    list_filter   = ['tenant', 'category', 'active', 'weighted']
    search_fields = ['name', 'sku', 'barcode']
    list_editable = ['price', 'stock', 'active']
    ordering      = ['name']


@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    list_display  = ['product', 'tenant', 'batch_number', 'remaining_quantity', 'expiry_date', 'received_at']
    list_filter   = ['tenant', 'expiry_date']
    search_fields = ['batch_number', 'product__name']
    ordering      = ['expiry_date']
    autocomplete_fields = ['product']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display  = ['product', 'tenant', 'movement_type', 'qty', 'sale', 'created_at']
    list_filter   = ['tenant', 'movement_type']
    search_fields = ['product__name']
    readonly_fields = ['created_at']


class SaleItemInline(admin.TabularInline):
    model           = SaleItem
    extra           = 0
    fields          = ['product', 'product_name', 'qty', 'price_each', 'line_total']
    readonly_fields = ['line_total']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display    = ['__str__', 'tenant', 'cashier_display', 'branch', 'terminal', 'total', 'method', 'status', 'created_at']
    list_filter     = ['tenant', 'method', 'status', 'offline']
    search_fields   = ['cashier__username', 'cashier__first_name', 'cashier__last_name', 'branch__name', 'terminal__name']
    inlines         = [SaleItemInline]
    readonly_fields = ['created_at']

    @admin.display(description='Cashier')
    def cashier_display(self, obj):
        if obj.cashier:
            return obj.cashier.get_full_name() or obj.cashier.username
        return '—'
