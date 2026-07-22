from django.db.models import Max
from rest_framework import serializers

from pos.services import units as units_svc
from recipes.models import Recipe, RecipeLine, RecipeVersion, ProductVariant
from recipes.services import costing as recipes_costing_svc


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


class RecipeSerializer(serializers.ModelSerializer):
    """The BOM container for a product or one of its variants (nested under
    /products/{pk}/recipes/). `product` comes from the URL, never the body.
    """

    variant_name = serializers.CharField(source='variant.name', read_only=True, default='')
    active_version_id = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            'id', 'variant', 'variant_name', 'active_version_id',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'variant_name', 'active_version_id', 'created_at', 'updated_at']

    def get_active_version_id(self, obj):
        version = obj.versions.filter(status=RecipeVersion.Status.ACTIVE).first()
        return version.id if version else None

    def validate_variant(self, value):
        product = self.context.get('product')
        if value is not None and product is not None and value.product_id != product.id:
            raise serializers.ValidationError("variant must belong to this recipe's product.")
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        if value is not None and tenant is not None and value.tenant_id != tenant.id:
            raise serializers.ValidationError("variant must belong to the caller's tenant.")
        return value


class RecipeLineSerializer(serializers.ModelSerializer):
    """One ingredient line of a `RecipeVersion`. `component_unit` is
    optional — when omitted, the service layer resolves it to the
    component's own base `ProductUnit`. `qty_base` is always server-
    computed (via `pos.services.units.convert_to_base`), never accepted
    from the client."""

    component_product_name = serializers.CharField(source='component_product.name', read_only=True)
    component_unit_name = serializers.CharField(
        source='component_unit.unit.name', read_only=True, default='',
    )

    class Meta:
        model = RecipeLine
        fields = [
            'id', 'component_product', 'component_product_name',
            'component_unit', 'component_unit_name',
            'entered_qty', 'qty_base', 'sort_order', 'is_active',
        ]
        read_only_fields = ['id', 'component_product_name', 'component_unit_name', 'qty_base']

    def validate_entered_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError('entered_qty must be > 0.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        component_product = attrs.get('component_product')
        component_unit = attrs.get('component_unit')
        if tenant is not None:
            if component_product is not None and component_product.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {'component_product': "must belong to the caller's tenant."},
                )
            if component_unit is not None and component_unit.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {'component_unit': "must belong to the caller's tenant."},
                )
        if (
            component_unit is not None and component_product is not None
            and component_unit.product_id != component_product.id
        ):
            raise serializers.ValidationError(
                {'component_unit': 'must belong to the same product as component_product.'},
            )
        return attrs


class RecipeVersionSerializer(serializers.ModelSerializer):
    """A versioned snapshot of a recipe's component lines (nested under
    /products/{pk}/recipes/{recipe_pk}/versions/). Always created as
    DRAFT — use the dedicated activate action to promote a version to
    ACTIVE (archiving whatever was previously active).
    """

    lines = RecipeLineSerializer(many=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RecipeVersion
        fields = [
            'id', 'version_no', 'status', 'status_display',
            'created_by', 'created_at', 'updated_at', 'lines',
        ]
        read_only_fields = [
            'id', 'version_no', 'status', 'status_display',
            'created_by', 'created_at', 'updated_at',
        ]

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError('at least one line is required.')
        return lines

    def create(self, validated_data):
        recipe = self.context['recipe']
        request = self.context.get('request')
        tenant = getattr(getattr(request, 'user', None), 'tenant', None)
        lines_data = validated_data.pop('lines')

        component_products = [ld['component_product'] for ld in lines_data]
        try:
            recipes_costing_svc.validate_recipe_lines(
                product=recipe.product, component_products=component_products,
            )
        except recipes_costing_svc.RecipeError as exc:
            raise serializers.ValidationError(str(exc))

        next_no = (recipe.versions.aggregate(m=Max('version_no'))['m'] or 0) + 1
        version = RecipeVersion.objects.create(
            tenant=tenant, recipe=recipe, version_no=next_no,
            status=RecipeVersion.Status.DRAFT,
            created_by=getattr(request, 'user', None),
        )
        for idx, line_data in enumerate(lines_data):
            component_product = line_data['component_product']
            component_unit = line_data.get('component_unit')
            if component_unit is None:
                component_unit = units_svc.get_base_product_unit(component_product)
            if component_unit is None:
                raise serializers.ValidationError(
                    f'component "{component_product.name}" has no configured unit yet — '
                    f'add a ProductUnit for it first.',
                )
            entered_qty = line_data['entered_qty']
            try:
                qty_base = units_svc.convert_to_base(
                    product=component_product, qty=entered_qty, product_unit=component_unit,
                )
            except units_svc.UnitConversionError as exc:
                raise serializers.ValidationError(str(exc))
            RecipeLine.objects.create(
                tenant=tenant, recipe_version=version,
                component_product=component_product, component_unit=component_unit,
                entered_qty=entered_qty, qty_base=qty_base,
                sort_order=line_data.get('sort_order', idx),
                is_active=line_data.get('is_active', True),
            )
        return version
