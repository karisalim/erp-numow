from rest_framework import serializers

from recipes.models import ProductVariant


class ProductVariantSerializer(serializers.ModelSerializer):
    """A size/option variant of a product (nested under
    /products/{pk}/variants/). `product` comes from the URL (view passes
    it via `save(product=..)`), never from the body — same convention as
    `ProductUnitSerializer`."""

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'name', 'sku', 'plu', 'price', 'sort_order',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError('price must be >= 0.')
        return value

    def validate_name(self, value):
        request = self.context.get('request')
        product = self.context.get('product')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if tenant is None or product is None:
            return value
        qs = ProductVariant.objects.filter(tenant=tenant, product=product, name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'A variant with this name already exists for this product.',
            )
        return value
