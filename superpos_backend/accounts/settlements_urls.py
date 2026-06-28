"""Phase 1.5 Slice G — settlement document routes.

Mounted at /api/customer-receipts/ and /api/supplier-payments/ in the
top-level URLconf. Both surfaces support GET (list + detail) and POST
(create), but never DELETE — receipts and payments are posted documents
and only get reversed via a future compensating-document slice.

See `accounts.services.customer_receipts` /
`accounts.services.supplier_payments` for the posting contract that the
POST endpoint here is a thin shell over.
"""

from django.urls import path

from .views import (
    CustomerReceiptDetailView,
    CustomerReceiptListCreateView,
    SupplierPaymentDetailView,
    SupplierPaymentListCreateView,
)


customer_receipt_urlpatterns = [
    path('',           CustomerReceiptListCreateView.as_view(), name='customer-receipt-list'),
    path('<int:pk>/',  CustomerReceiptDetailView.as_view(),     name='customer-receipt-detail'),
]


supplier_payment_urlpatterns = [
    path('',           SupplierPaymentListCreateView.as_view(), name='supplier-payment-list'),
    path('<int:pk>/',  SupplierPaymentDetailView.as_view(),     name='supplier-payment-detail'),
]
