from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    BranchDetailView, BranchListCreateView,
    LoginView, MeView, TenantSettingsView, TenantTranslationsView,
    UserListCreateView, UserDetailView,
)

urlpatterns = [
    path('login/',             LoginView.as_view(),             name='auth-login'),
    path('token/refresh/',     TokenRefreshView.as_view(),      name='auth-refresh'),
    path('me/',                MeView.as_view(),                 name='auth-me'),
    path('users/',             UserListCreateView.as_view(),     name='user-list'),
    path('users/<int:pk>/',    UserDetailView.as_view(),         name='user-detail'),
    path('branches/',          BranchListCreateView.as_view(),   name='branch-list'),
    path('branches/<int:pk>/', BranchDetailView.as_view(),       name='branch-detail'),
    path('tenant/settings/',   TenantSettingsView.as_view(),     name='tenant-settings'),
    path('tenant/translations/<str:lang>/',
         TenantTranslationsView.as_view(),                       name='tenant-translations'),
]
