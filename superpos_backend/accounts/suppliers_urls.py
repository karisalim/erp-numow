"""v3.6 supplier master-data routes mounted at /api/suppliers/.

MASTER_DATA_CONTRACT.md §10. AP-movement + supplier-payment endpoints
are a later slice; this file is CRUD + deactivate only.
"""

from django.urls import path

from .views import (
    SupplierDeactivateView,
    SupplierDetailView,
    SupplierListCreateView,
)


urlpatterns = [
    path('',                       SupplierListCreateView.as_view(), name='supplier-list'),
    path('<int:pk>/',              SupplierDetailView.as_view(),     name='supplier-detail'),
    path('<int:pk>/deactivate/',   SupplierDeactivateView.as_view(), name='supplier-deactivate'),
]
