from django.urls import path

from . import views

urlpatterns = [
    # Categories
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),

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
    path('dashboard/top-products/', views.dashboard_top_products, name='dashboard-top-products'),
    path('dashboard/low-stock/',    views.dashboard_low_stock,    name='dashboard-low-stock'),
    path('dashboard/daily-stats/',  views.dashboard_daily_stats,  name='dashboard-daily-stats'),
]
