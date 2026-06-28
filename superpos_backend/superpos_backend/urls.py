from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views import (
    CustomerARMovementListView,
    SupplierAPMovementListView,
)
from accounts.settlements_urls import (
    customer_receipt_urlpatterns,
    supplier_payment_urlpatterns,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/',     include('accounts.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/branches/',  include('accounts.branches_urls')),
    path('api/finance/',   include('accounts.finance_urls')),
    path('api/customers/', include('accounts.customers_urls')),
    path('api/suppliers/', include('accounts.suppliers_urls')),

    # Phase 1.5 Slice F — tenant-wide flat AR/AP ledger streams.
    # Mounted inline since each prefix only has one route — adding a
    # dedicated URL module per single-endpoint prefix is overkill.
    path('api/customer-ar/movements/', CustomerARMovementListView.as_view(), name='customer-ar-movement-list'),
    path('api/supplier-ap/movements/', SupplierAPMovementListView.as_view(), name='supplier-ap-movement-list'),

    # Phase 1.5 Slice G — settlement document endpoints.
    path('api/customer-receipts/', include((customer_receipt_urlpatterns, 'customer_receipts'))),
    path('api/supplier-payments/', include((supplier_payment_urlpatterns, 'supplier_payments'))),

    path('api/',           include('pos.urls')),

    # OpenAPI schema + Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
