from django.urls import path

from recipes import views

urlpatterns = [
    path('products/<int:product_pk>/variants/',              views.ProductVariantListCreateView.as_view(), name='product-variant-list'),
    path('products/<int:product_pk>/variants/<int:pk>/',     views.ProductVariantDetailView.as_view(),     name='product-variant-detail'),
    path('products/<int:product_pk>/variants/<int:pk>/deactivate/', views.ProductVariantDeactivateView.as_view(), name='product-variant-deactivate'),
]
