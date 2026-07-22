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

    path('catalog/modifier-groups/',                        views.ModifierGroupListCreateView.as_view(), name='modifier-group-list'),
    path('catalog/modifier-groups/<int:pk>/',                views.ModifierGroupDetailView.as_view(),     name='modifier-group-detail'),
    path('catalog/modifier-groups/<int:pk>/deactivate/',     views.ModifierGroupDeactivateView.as_view(), name='modifier-group-deactivate'),
    path(
        'catalog/modifier-groups/<int:group_pk>/options/',
        views.ModifierOptionListCreateView.as_view(), name='modifier-option-list',
    ),
    path(
        'catalog/modifier-groups/<int:group_pk>/options/<int:pk>/',
        views.ModifierOptionDetailView.as_view(), name='modifier-option-detail',
    ),
    path(
        'catalog/modifier-groups/<int:group_pk>/options/<int:pk>/deactivate/',
        views.ModifierOptionDeactivateView.as_view(), name='modifier-option-deactivate',
    ),
    path(
        'catalog/modifier-options/<int:option_pk>/consumptions/',
        views.ModifierOptionConsumptionListCreateView.as_view(), name='modifier-option-consumption-list',
    ),
    path(
        'catalog/modifier-options/<int:option_pk>/consumptions/<int:pk>/',
        views.ModifierOptionConsumptionDetailView.as_view(), name='modifier-option-consumption-detail',
    ),

    path(
        'products/<int:product_pk>/modifier-groups/',
        views.ProductModifierGroupListCreateView.as_view(), name='product-modifier-group-list',
    ),
    path(
        'products/<int:product_pk>/modifier-groups/<int:pk>/',
        views.ProductModifierGroupDetailView.as_view(), name='product-modifier-group-detail',
    ),
]
