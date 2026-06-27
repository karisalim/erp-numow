"""v3.6 customer master-data routes mounted at /api/customers/.

MASTER_DATA_CONTRACT.md §10 (Customer/Supplier basics). The full
AR-movement / receipt-allocation surface lives in a later slice; this
file only exposes CRUD + deactivate for the master record itself.
"""

from django.urls import path

from .views import (
    CustomerDeactivateView,
    CustomerDetailView,
    CustomerListCreateView,
)


urlpatterns = [
    path('',                       CustomerListCreateView.as_view(), name='customer-list'),
    path('<int:pk>/',              CustomerDetailView.as_view(),     name='customer-detail'),
    path('<int:pk>/deactivate/',   CustomerDeactivateView.as_view(), name='customer-deactivate'),
]
