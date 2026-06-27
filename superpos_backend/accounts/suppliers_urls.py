"""v3.6 supplier master-data routes mounted at /api/suppliers/.

MASTER_DATA_CONTRACT.md §10. AP-movement + supplier-payment endpoints
are a later slice; this file is CRUD + deactivate only.
"""

from django.urls import path

from .views import (
    SupplierBalanceView,
    SupplierDeactivateView,
    SupplierDetailView,
    SupplierListCreateView,
    SupplierStatementView,
)


urlpatterns = [
    path('',                       SupplierListCreateView.as_view(), name='supplier-list'),
    path('<int:pk>/',              SupplierDetailView.as_view(),     name='supplier-detail'),
    path('<int:pk>/deactivate/',   SupplierDeactivateView.as_view(), name='supplier-deactivate'),
    # Phase 1.5 Slice F — AP ledger reads.
    path('<int:pk>/statement/',    SupplierStatementView.as_view(),  name='supplier-statement'),
    path('<int:pk>/balance/',      SupplierBalanceView.as_view(),    name='supplier-balance'),
]
