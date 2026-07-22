from django.urls import path

from . import views

urlpatterns = [
    # Categories
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),

    # Catalog — hierarchical category trees (Sprint 2 Batch 2, MASTER_DATA_CONTRACT §3)
    path('catalog/sales-categories/',                     views.SalesCategoryListCreateView.as_view(),     name='sales-category-list'),
    path('catalog/sales-categories/<int:pk>/',            views.SalesCategoryDetailView.as_view(),         name='sales-category-detail'),
    path('catalog/sales-categories/<int:pk>/deactivate/', views.SalesCategoryDeactivateView.as_view(),     name='sales-category-deactivate'),
    path('catalog/inventory-categories/',                     views.InventoryCategoryListCreateView.as_view(), name='inventory-category-list'),
    path('catalog/inventory-categories/<int:pk>/',            views.InventoryCategoryDetailView.as_view(),     name='inventory-category-detail'),
    path('catalog/inventory-categories/<int:pk>/deactivate/', views.InventoryCategoryDeactivateView.as_view(), name='inventory-category-deactivate'),

    # Catalog — dynamic units (Sprint 2 Batch 1, MASTER_DATA_CONTRACT §2.4)
    path('catalog/unit-groups/',                     views.UnitGroupListCreateView.as_view(), name='unit-group-list'),
    path('catalog/unit-groups/<int:pk>/',            views.UnitGroupDetailView.as_view(),     name='unit-group-detail'),
    path('catalog/unit-groups/<int:pk>/deactivate/', views.UnitGroupDeactivateView.as_view(), name='unit-group-deactivate'),
    path('catalog/units/',                           views.UnitListCreateView.as_view(),      name='unit-list'),
    path('catalog/units/<int:pk>/',                  views.UnitDetailView.as_view(),          name='unit-detail'),
    path('catalog/units/<int:pk>/deactivate/',       views.UnitDeactivateView.as_view(),      name='unit-deactivate'),

    # Catalog — standard unit codes (Sprint 2 Phase 1.5, UN/CEFACT Rec 20 subset)
    path('catalog/standard-unit-codes/', views.StandardUnitCodeListView.as_view(), name='standard-unit-code-list'),

    # Catalog — price tiers (Sprint 2 Batch 4 remainder, MASTER_DATA_CONTRACT §2)
    path('catalog/price-tiers/',                     views.PriceTierListCreateView.as_view(), name='price-tier-list'),
    path('catalog/price-tiers/<int:pk>/',            views.PriceTierDetailView.as_view(),     name='price-tier-detail'),
    path('catalog/price-tiers/<int:pk>/deactivate/', views.PriceTierDeactivateView.as_view(), name='price-tier-deactivate'),

    # Products
    path('products/',                       views.ProductListCreateView.as_view(), name='product-list'),
    path('products/export/',                views.products_export,                 name='product-export'),
    path('products/import/',                views.products_import,                 name='product-import'),
    path('products/barcode/<str:barcode>/', views.product_by_barcode,              name='product-barcode'),
    path('products/scan/<str:barcode>/',    views.product_scan,                    name='product-scan'),
    path('products/<int:pk>/',              views.ProductDetailView.as_view(),     name='product-detail'),
    path('products/<int:pk>/stock/',        views.product_stock_update,            name='product-stock'),
    # Phase 1.5 Slice D — per-product ledger views (read-only).
    path('products/<int:pk>/stock-movements/', views.ProductStockMovementListView.as_view(), name='product-stock-movements'),
    path('products/<int:pk>/stock-balance/',   views.ProductStockBalanceView.as_view(),      name='product-stock-balance'),
    # Phase 1.5 Slice J — per-warehouse balances for one product (read-only).
    path('products/<int:pk>/warehouse-stocks/', views.ProductWarehouseStockView.as_view(),    name='product-warehouse-stock'),
    # Sprint 3 Batch 4 — per-product AVCO audit trail (read-only).
    path('products/<int:pk>/cost-movements/',   views.ProductCostMovementListView.as_view(),  name='product-cost-movements'),
    # Sprint 4 Batch 4 — export the same audit trail as CSV/Excel/PDF
    # (query param is `export_format`, not `format` — DRF reserves that name).
    path('products/<int:pk>/cost-movements/export/', views.product_cost_movements_export,      name='product-cost-movements-export'),
    # Sprint 2 Batch 1 — per-product unit mappings + per-pack barcodes.
    path('products/<int:product_pk>/units/',          views.ProductUnitListCreateView.as_view(),        name='product-unit-list'),
    path('products/<int:product_pk>/units/<int:pk>/', views.ProductUnitDetailView.as_view(),            name='product-unit-detail'),
    path('products/<int:product_pk>/barcodes/',       views.ProductBarcodeUnitListCreateView.as_view(), name='product-barcode-list'),
    # Sprint 2 Batch 4 remainder — per-(product_unit, price_tier) prices.
    path('products/<int:product_pk>/units/<int:unit_pk>/tier-prices/',          views.ProductUnitTierPriceListCreateView.as_view(), name='product-unit-tier-price-list'),
    path('products/<int:product_pk>/units/<int:unit_pk>/tier-prices/<int:pk>/', views.ProductUnitTierPriceDetailView.as_view(),     name='product-unit-tier-price-detail'),

    # Inventory — batches (CRUD)
    path('inventory/batches/',          views.InventoryBatchListCreateView.as_view(), name='batch-list'),
    path('inventory/batches/<int:pk>/', views.InventoryBatchDetailView.as_view(),     name='batch-detail'),

    # Inventory — actions
    path('inventory/purchase/', views.purchase_receipt, name='inventory-purchase'),
    path('inventory/adjust/',   views.stock_adjustment, name='inventory-adjust'),
    path('inventory/alerts/',   views.inventory_alerts, name='inventory-alerts'),

    # Stock movements — per-product audit trail + ad-hoc receive/adjust
    path('stock-movements/', views.StockMovementListCreateView.as_view(), name='stock-movement-list'),

    # Inventory — Warehouses (Phase 1.5 Dynamic Warehouses foundation)
    path('inventory/warehouses/',                     views.WarehouseListCreateView.as_view(), name='warehouse-list'),
    path('inventory/warehouses/<int:pk>/',            views.WarehouseDetailView.as_view(),     name='warehouse-detail'),
    path('inventory/warehouses/<int:pk>/deactivate/', views.WarehouseDeactivateView.as_view(), name='warehouse-deactivate'),

    # Inventory — Branch↔Warehouse links (role-based)
    path('inventory/branch-warehouses/',                     views.BranchWarehouseListCreateView.as_view(), name='branch-warehouse-list'),
    path('inventory/branch-warehouses/<int:pk>/',            views.BranchWarehouseDetailView.as_view(),     name='branch-warehouse-detail'),
    path('inventory/branch-warehouses/<int:pk>/deactivate/', views.BranchWarehouseDeactivateView.as_view(), name='branch-warehouse-deactivate'),

    # Inventory — per-warehouse stock balances (Phase 1.5 Slice J, read-only)
    path('inventory/warehouse-stocks/',           views.WarehouseStockListView.as_view(), name='warehouse-stock-list'),
    path('inventory/warehouses/<int:pk>/stock/', views.WarehouseInventoryView.as_view(), name='warehouse-inventory'),

    # Purchase Invoices (Phase 1.5 Slice H — create-and-post stock purchases)
    path('purchase-invoices/',           views.PurchaseInvoiceListCreateView.as_view(), name='purchase-invoice-list'),
    path('purchase-invoices/<int:pk>/',  views.PurchaseInvoiceDetailView.as_view(),     name='purchase-invoice-detail'),

    # Sales — list / create
    path('sales/',        views.SaleListCreateView.as_view(), name='sale-list'),
    path('sales/export/', views.sales_export,                 name='sale-export'),

    # Sales — detail & void by pk (kept for backward compatibility)
    path('sales/<int:pk>/',          views.SaleDetailView.as_view(), name='sale-detail-pk'),
    path('sales/<int:pk>/void/',     views.void_sale,                name='sale-void-pk'),
    path('sales/<int:pk>/receipt/',  views.sale_receipt,             name='sale-receipt-pk'),

    # Sales — detail & void by UUID (preferred public identifier)
    path('sales/<uuid:sale_uuid>/',         views.SaleDetailView.as_view(), name='sale-detail'),
    path('sales/<uuid:sale_uuid>/void/',    views.void_sale,                name='sale-void'),
    path('sales/<uuid:sale_uuid>/receipt/', views.sale_receipt,             name='sale-receipt'),

    # Dashboard
    path('dashboard/summary/',      views.dashboard_summary,      name='dashboard-summary'),
    path('dashboard/trend/',        views.dashboard_trend,        name='dashboard-trend'),
    path('dashboard/top-products/', views.dashboard_top_products, name='dashboard-top-products'),
    path('dashboard/low-stock/',    views.dashboard_low_stock,    name='dashboard-low-stock'),
    path('dashboard/daily-stats/',  views.dashboard_daily_stats,  name='dashboard-daily-stats'),

    # Recipe / food-cost reporting (Sprint 5 Batch 6)
    path('reports/recipe-profitability/',   views.recipe_profitability,          name='recipe-profitability'),
    path('reports/ingredient-consumption/', views.ingredient_consumption_report, name='ingredient-consumption-report'),
]
