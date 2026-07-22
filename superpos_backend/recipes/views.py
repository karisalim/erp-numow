from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response

from accounts.permissions import IsCashierOrAbove, IsManagerOrAbove
from pos.models import Product
from pos.views import TenantMixin
from recipes.models import (
    ModifierGroup, ModifierOption, ModifierOptionConsumption,
    ProductModifierGroup, ProductVariant, Recipe, RecipeVersion,
)
from recipes.serializers import (
    ModifierGroupSerializer, ModifierOptionConsumptionSerializer,
    ModifierOptionSerializer, ProductModifierGroupSerializer,
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


# ── Modifiers (Sprint 5 Batch 4) ─────────────────────────────────────────────
# ModifierGroup is tenant-scoped and flat (same conventions as PriceTier);
# ModifierOption nests one level under it; ProductModifierGroup is the
# product<->group attach/detach link; ModifierOptionConsumption nests one
# level under an option.

class ModifierGroupListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = ModifierGroup.objects.all()
    serializer_class = ModifierGroupSerializer
    search_fields    = ['name']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ModifierGroupDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a modifier group. No DELETE — deactivate instead."""

    queryset          = ModifierGroup.objects.all()
    serializer_class  = ModifierGroupSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ModifierGroupDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = ModifierGroup.objects.all()
    serializer_class   = ModifierGroupSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        group = self.get_object()
        if group.is_active:
            group.is_active = False
            group.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(group).data)


class _ModifierGroupScopedMixin(TenantMixin):
    """Resolves the parent modifier group from `group_pk`, tenant-scoped."""

    def get_modifier_group(self):
        qs = ModifierGroup.objects.all()
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['group_pk'])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['modifier_group'] = self.get_modifier_group()
        return ctx

    def perform_create(self, serializer):
        tenant = self._tenant()
        modifier_group = self.get_modifier_group()
        if tenant:
            serializer.save(tenant=tenant, modifier_group=modifier_group)
        else:
            serializer.save(modifier_group=modifier_group)


class ModifierOptionListCreateView(_ModifierGroupScopedMixin, generics.ListCreateAPIView):
    queryset         = ModifierOption.objects.all()
    serializer_class = ModifierOptionSerializer
    ordering         = ['sort_order', 'name']

    def get_queryset(self):
        return super().get_queryset().filter(modifier_group_id=self.kwargs['group_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ModifierOptionDetailView(_ModifierGroupScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one option. No DELETE — deactivate via the dedicated action."""

    queryset          = ModifierOption.objects.all()
    serializer_class  = ModifierOptionSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(modifier_group_id=self.kwargs['group_pk'])

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ModifierOptionDeactivateView(_ModifierGroupScopedMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = ModifierOption.objects.all()
    serializer_class   = ModifierOptionSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(modifier_group_id=self.kwargs['group_pk'])

    def post(self, request, *args, **kwargs):
        option = self.get_object()
        if option.is_active:
            option.is_active = False
            option.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(option).data)


class ProductModifierGroupListCreateView(_ProductScopedMixin, generics.ListCreateAPIView):
    """GET/POST which modifier groups a product offers. POST attaches
    (creates the link); DELETE on the detail view detaches — this is a
    pure link table (no historical data worth soft-deleting)."""

    queryset         = ProductModifierGroup.objects.select_related('modifier_group').all()
    serializer_class = ProductModifierGroupSerializer
    ordering         = ['sort_order', 'id']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductModifierGroupDetailView(_ProductScopedMixin, generics.RetrieveDestroyAPIView):
    """GET one link; DELETE detaches the modifier group from the product."""

    queryset          = ProductModifierGroup.objects.select_related('modifier_group').all()
    serializer_class  = ProductModifierGroupSerializer
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class _ModifierOptionScopedMixin(TenantMixin):
    """Resolves the parent modifier option from `option_pk`, tenant-scoped."""

    def get_modifier_option(self):
        qs = ModifierOption.objects.all()
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['option_pk'])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['modifier_option'] = self.get_modifier_option()
        return ctx


class ModifierOptionConsumptionListCreateView(_ModifierOptionScopedMixin, generics.ListCreateAPIView):
    queryset         = ModifierOptionConsumption.objects.select_related(
        'component_product', 'variant',
    ).all()
    serializer_class = ModifierOptionConsumptionSerializer
    ordering         = ['id']
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(modifier_option_id=self.kwargs['option_pk'])


class ModifierOptionConsumptionDetailView(_ModifierOptionScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one consumption row. No DELETE — deactivate via PATCH(is_active)."""

    queryset            = ModifierOptionConsumption.objects.select_related(
        'component_product', 'variant',
    ).all()
    serializer_class    = ModifierOptionConsumptionSerializer
    http_method_names  = ['get', 'patch', 'head', 'options']
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return super().get_queryset().filter(modifier_option_id=self.kwargs['option_pk'])
