from django.urls import path

from recipes import views

urlpatterns = [
    path('products/<int:product_pk>/variants/',              views.ProductVariantListCreateView.as_view(), name='product-variant-list'),
    path('products/<int:product_pk>/variants/<int:pk>/',     views.ProductVariantDetailView.as_view(),     name='product-variant-detail'),
    path('products/<int:product_pk>/variants/<int:pk>/deactivate/', views.ProductVariantDeactivateView.as_view(), name='product-variant-deactivate'),

    path('products/<int:product_pk>/recipes/',              views.RecipeListCreateView.as_view(), name='recipe-list'),
    path('products/<int:product_pk>/recipes/<int:pk>/',     views.RecipeDetailView.as_view(),     name='recipe-detail'),
    path(
        'products/<int:product_pk>/recipes/<int:recipe_pk>/versions/',
        views.RecipeVersionListCreateView.as_view(), name='recipe-version-list',
    ),
    path(
        'products/<int:product_pk>/recipes/<int:recipe_pk>/versions/<int:pk>/',
        views.RecipeVersionDetailView.as_view(), name='recipe-version-detail',
    ),
    path(
        'products/<int:product_pk>/recipes/<int:recipe_pk>/versions/<int:pk>/activate/',
        views.RecipeVersionActivateView.as_view(), name='recipe-version-activate',
    ),
]
