from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response

from accounts.permissions import IsCashierOrAbove, IsManagerOrAbove
from pos.models import Product
from pos.views import TenantMixin
from recipes.models import ProductVariant
from recipes.serializers import ProductVariantSerializer


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
