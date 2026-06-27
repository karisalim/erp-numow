"""v3.6 master-data routes for /api/branches/.

Mounted at the top of the URL tree (not under /api/auth/ or /api/accounts/)
to match MASTER_DATA_CONTRACT.md §4.4. The legacy /api/auth/branches/ and
/api/accounts/branches/ mounts continue to serve the legacy `BranchSerializer`
shape so existing UI code is not broken — both surfaces hit the same model.
"""

from django.urls import path

from .views import (
    BranchDeactivateView,
    BranchPaymentMethodDeactivateView,
    BranchPaymentMethodDetailView,
    BranchPaymentMethodListCreateView,
    BranchSettingsView,
    BranchUsersView,
    BranchV2DetailView,
    BranchV2ListCreateView,
)


urlpatterns = [
    path('',                       BranchV2ListCreateView.as_view(), name='branch-v2-list'),
    path('<int:pk>/',              BranchV2DetailView.as_view(),     name='branch-v2-detail'),
    path('<int:pk>/deactivate/',   BranchDeactivateView.as_view(),   name='branch-v2-deactivate'),
    path('<int:pk>/settings/',     BranchSettingsView.as_view(),     name='branch-v2-settings'),
    path('<int:pk>/users/',        BranchUsersView.as_view(),        name='branch-v2-users'),

    # Phase 1.5 Slice C — per-branch payment-method routing.
    path('<int:branch_pk>/payment-methods/',                     BranchPaymentMethodListCreateView.as_view(), name='branch-payment-method-list'),
    path('<int:branch_pk>/payment-methods/<int:pk>/',            BranchPaymentMethodDetailView.as_view(),     name='branch-payment-method-detail'),
    path('<int:branch_pk>/payment-methods/<int:pk>/deactivate/', BranchPaymentMethodDeactivateView.as_view(), name='branch-payment-method-deactivate'),
]
