"""v3.6 finance/payment-method routes mounted at /api/finance/.

Implements MASTER_DATA_CONTRACT.md §1.4 except the branch-scoped routes
(those live under /api/branches/{branch_id}/payment-methods/ — see
`branches_urls.py`).
"""

from django.urls import path

from .views import (
    FinancialAccountBalanceView,
    FinancialAccountDeactivateView,
    FinancialAccountDetailView,
    FinancialAccountListCreateView,
    FinancialAccountMovementListView,
    FinancialAccountStatementView,
    PaymentMethodDeactivateView,
    PaymentMethodDetailView,
    PaymentMethodListCreateView,
)


urlpatterns = [
    path('accounts/',                     FinancialAccountListCreateView.as_view(), name='finance-account-list'),
    path('accounts/<int:pk>/',            FinancialAccountDetailView.as_view(),     name='finance-account-detail'),
    path('accounts/<int:pk>/deactivate/', FinancialAccountDeactivateView.as_view(), name='finance-account-deactivate'),
    # Phase 1.5 Slice D — read-only movement views.
    path('accounts/<int:pk>/movements/',  FinancialAccountStatementView.as_view(),  name='finance-account-statement'),
    path('accounts/<int:pk>/balance/',    FinancialAccountBalanceView.as_view(),    name='finance-account-balance'),
    path('movements/',                    FinancialAccountMovementListView.as_view(), name='finance-movement-list'),

    path('payment-methods/',                     PaymentMethodListCreateView.as_view(), name='payment-method-list'),
    path('payment-methods/<int:pk>/',            PaymentMethodDetailView.as_view(),     name='payment-method-detail'),
    path('payment-methods/<int:pk>/deactivate/', PaymentMethodDeactivateView.as_view(), name='payment-method-deactivate'),
]
