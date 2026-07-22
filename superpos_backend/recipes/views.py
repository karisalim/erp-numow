from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response

from accounts.permissions import IsCashierOrAbove, IsManagerOrAbove
from pos.models import Product
from pos.views import TenantMixin
from recipes.models import ProductVariant, Recipe, RecipeVersion
from recipes.serializers import (
    ProductVariantSerializer, RecipeSerializer, RecipeVersionSerializer,
)
from recipes.services import costing as recipes_costing_svc


class _ProductScopedMixin(TenantMixin):
    """Resolves the parent product from `product_pk`, tenant-scoped —
    mirrors `pos.views._ProductScopedMixin` exactly (that one can't be
    reused directly: it's private/module-local to `pos.views`, and
    duplicating this ~15-line resolver is cheaper than exporting a new
    cross-app contract for it)."""

    def get_product(self):
        qs = Product.objects.all()
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['product_pk'])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['product'] = self.get_product()
        return ctx

    def perform_create(self, serializer):
        tenant = self._tenant()
        if tenant:
            serializer.save(tenant=tenant, product=self.get_product())
        else:
            serializer.save(product=self.get_product())


class ProductVariantListCreateView(_ProductScopedMixin, generics.ListCreateAPIView):
    queryset         = ProductVariant.objects.all()
    serializer_class = ProductVariantSerializer
    ordering         = ['sort_order', 'name']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductVariantDetailView(_ProductScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one variant. No DELETE — deactivate via the dedicated action."""

    queryset          = ProductVariant.objects.all()
    serializer_class  = ProductVariantSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductVariantDeactivateView(_ProductScopedMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = ProductVariant.objects.all()
    serializer_class   = ProductVariantSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def post(self, request, *args, **kwargs):
        variant = self.get_object()
        if variant.is_active:
            variant.is_active = False
            variant.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(variant).data)


# ── Recipes (Sprint 5 Batch 3) ──────────────────────────────────────────────
# Recipe editing is Manager+-only throughout (matches the Units/Price-Tiers/
# Categories admin precedent) — there is no cashier-writable path here, but
# reads stay IsCashierOrAbove so a POS screen can display a recipe's active
# version if a future batch needs to.

class RecipeListCreateView(_ProductScopedMixin, generics.ListCreateAPIView):
    queryset         = Recipe.objects.select_related('variant').all()
    serializer_class = RecipeSerializer
    ordering         = ['id']

    def get_queryset(self):
        qs = super().get_queryset().filter(product_id=self.kwargs['product_pk'])
        variant_id = self.request.query_params.get('variant_id')
        if variant_id is not None:
            qs = qs.filter(variant_id=variant_id)
        return qs

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class RecipeDetailView(_ProductScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one recipe. No DELETE — deactivate via PATCH(is_active)."""

    queryset          = Recipe.objects.select_related('variant').all()
    serializer_class  = RecipeSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class _RecipeVersionScopedMixin(TenantMixin):
    """Resolves the parent recipe (itself scoped to `product_pk`), tenant-
    scoped — same two-level nesting shape as `pos.views
    ._ProductUnitScopedMixin`."""

    def get_recipe(self):
        qs = Recipe.objects.filter(product_id=self.kwargs['product_pk'])
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['recipe_pk'])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['recipe'] = self.get_recipe()
        return ctx


class RecipeVersionListCreateView(_RecipeVersionScopedMixin, generics.ListCreateAPIView):
    """GET/POST versions of a recipe. POST always creates a DRAFT — use
    RecipeVersionActivateView to promote one to ACTIVE. Permissions are
    Manager+-only for both verbs (unlike most catalog CRUD): a recipe's
    exact quantities are a sensitive editorial detail, not a routine
    catalog read."""

    queryset           = RecipeVersion.objects.prefetch_related('lines__component_product').all()
    serializer_class    = RecipeVersionSerializer
    ordering            = ['-version_no']
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(recipe_id=self.kwargs['recipe_pk'])


class RecipeVersionDetailView(_RecipeVersionScopedMixin, generics.RetrieveAPIView):
    queryset            = RecipeVersion.objects.prefetch_related('lines__component_product').all()
    serializer_class    = RecipeVersionSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(recipe_id=self.kwargs['recipe_pk'])


class RecipeVersionActivateView(_RecipeVersionScopedMixin, generics.GenericAPIView):
    """POST — activate this version, atomically archiving whatever was
    previously ACTIVE on the same recipe."""

    queryset            = RecipeVersion.objects.all()
    serializer_class    = RecipeVersionSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(recipe_id=self.kwargs['recipe_pk'])

    def post(self, request, *args, **kwargs):
        version = self.get_object()
        version = recipes_costing_svc.activate_recipe_version(version)
        return Response(self.get_serializer(version).data)
