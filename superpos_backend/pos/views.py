import csv
import io
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import (
    Branch, CustomerARMovement, FinancialAccountMovement,
)
from accounts.permissions import IsCashierOrAbove, IsManagerOrAbove
from accounts.services import account_movements as fa
from accounts.services import customer_ar as ar
from .filters import (
    BranchWarehouseFilter, InventoryCategoryFilter, InventoryCostMovementFilter,
    ProductFilter, SaleFilter, SalesCategoryFilter, StockMovementFilter,
    UnitFilter, UnitGroupFilter, WarehouseFilter, WarehouseStockFilter,
)
from .models import (
    AuditLog, BranchWarehouse, Category, InventoryBatch, InventoryCategory,
    InventoryCostMovement, PriceTier, Product, ProductBarcodeUnit, ProductUnit,
    ProductUnitTierPrice, PurchaseInvoice, Sale, SaleItem, SalesCategory,
    StockMovement, Unit, UnitGroup, Warehouse, WarehouseStock,
)
from .serializers import (
    BranchWarehouseSerializer,
    CategorySerializer,
    InventoryBatchSerializer,
    InventoryCategorySerializer,
    InventoryCostMovementSerializer,
    PriceTierSerializer,
    ProductBarcodeUnitSerializer,
    ProductSerializer,
    ProductStockUpdateSerializer,
    ProductUnitSerializer,
    ProductUnitTierPriceSerializer,
    PurchaseInvoiceSerializer,
    PurchaseReceiptSerializer,
    ReceiptSerializer,
    SaleListSerializer,
    SaleSerializer,
    SalesCategorySerializer,
    StockAdjustmentSerializer,
    StockMovementSerializer,
    UnitGroupSerializer,
    UnitSerializer,
    WarehouseSerializer,
    WarehouseStockSerializer,
)
from .services import barcode_resolution, costing, idempotency
from .services.product_types import ProductType, product_type_metadata
from .services.standard_units import StandardUnitCode


# ── Tenant isolation mixin ────────────────────────────────────────────────────

class TenantMixin:
    def _tenant(self):
        return getattr(self.request.user, 'tenant', None)

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

    def perform_create(self, serializer):
        tenant = self._tenant()
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save()


# ── Categories ────────────────────────────────────────────────────────────────

class CategoryListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields    = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


# ── Products ──────────────────────────────────────────────────────────────────

class ProductListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = Product.objects.select_related(
        'category', 'sales_category', 'inventory_category').all()
    serializer_class = ProductSerializer
    filterset_class  = ProductFilter
    search_fields    = ['name', 'barcode', 'sku']
    ordering_fields  = ['name', 'price', 'stock', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductDetailView(TenantMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset         = Product.objects.select_related(
        'category', 'sales_category', 'inventory_category').all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


@api_view(['GET'])
@permission_classes([IsCashierOrAbove])
def product_by_barcode(request, barcode):
    tenant = getattr(request.user, 'tenant', None)
    qs = Product.objects.filter(barcode=barcode, active=True)
    if tenant:
        qs = qs.filter(tenant=tenant)
    try:
        product = qs.get()
        return Response(ProductSerializer(product).data)
    except Product.DoesNotExist:
        return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)


def _parse_weight_encoded_barcode(barcode: str, prefix: str):
    """Decode a 13-digit scale-printed barcode of the form
    `PP PPPPP WWWWW C` — prefix (2) + PLU (5) + net-weight grams (5) + checksum.

    Returns `(plu, weight_kg)` on success, or `None` if the input doesn't
    structurally match. The checksum digit is intentionally not validated
    here — different scale brands use different schemes (EAN-13, Mettler,
    Bizerba) and we don't want to reject barcodes that wholesalers print
    with a non-standard check digit.
    """
    if not barcode or len(barcode) != 13 or not barcode.isdigit():
        return None
    if not prefix or not barcode.startswith(prefix):
        return None
    plu        = barcode[2:7]
    weight_str = barcode[7:12]
    try:
        weight_kg = Decimal(weight_str) / Decimal('1000')
    except (InvalidOperation, ValueError):
        return None
    return plu, weight_kg


@api_view(['GET'])
@permission_classes([IsCashierOrAbove])
def product_scan(request, barcode):
    """
    GET /api/products/scan/<barcode>/

    Single entry-point for the POS barcode scanner. Behaviour:

    1. If the barcode matches the tenant's weight-encoded scale prefix
       (default '23'), decode the embedded PLU + net weight and respond
       with the matching product plus the pre-calculated line total.
       Frontend should drop these straight into the cart with the
       provided `quantity` and `line_total` — no further math needed.

    2. Otherwise, fall back to a normal barcode lookup against
       `Product.barcode` (identical to `product_by_barcode`).

    Response shape (weight-encoded match):
        {
            "type":       "weight_encoded",
            "product":    { ...ProductSerializer payload... },
            "plu":        "09524",
            "quantity":   "0.144",
            "price_each": "140.00",
            "line_total": "20.16"
        }

    Response shape (plain barcode match):
        { "type": "barcode", "product": { ...ProductSerializer... } }
    """
    tenant = getattr(request.user, 'tenant', None)

    # Honour tenant config; fall back to '23' if admin hasn't set one.
    prefix = (getattr(tenant, 'scale_barcode_prefix', '') or '23').strip()
    parsed = _parse_weight_encoded_barcode(barcode, prefix)

    if parsed is not None:
        plu, weight_kg = parsed
        qs = Product.objects.filter(plu=plu, active=True)
        if tenant:
            qs = qs.filter(tenant=tenant)
        product = qs.first()
        if product is None:
            return Response(
                {'detail': f'No product matches PLU {plu}.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Quantize to 3dp on weight and 2dp on currency so the total written
        # to SaleItem.line_total matches what the receipt prints exactly —
        # downstream `sum(qty * price)` math is then a no-op rounding-wise.
        quantity   = weight_kg.quantize(Decimal('0.001'))
        line_total = (quantity * product.price).quantize(Decimal('0.01'))
        return Response({
            'type':       'weight_encoded',
            'product':    ProductSerializer(product).data,
            'plu':        plu,
            'quantity':   str(quantity),
            'price_each': str(product.price),
            'line_total': str(line_total),
        })

    resolved = barcode_resolution.resolve_barcode(tenant=tenant, code=barcode)
    if resolved is None:
        return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
    product, product_unit = resolved
    body = {'type': 'barcode', 'product': ProductSerializer(product).data}
    if product_unit is not None:
        body['product_unit'] = {
            'id': product_unit.id,
            'unit_id': product_unit.unit_id,
            'unit_name': product_unit.unit.name,
            'conversion_to_base': str(product_unit.conversion_to_base),
            'is_base': product_unit.is_base,
        }
    return Response(body)


@api_view(['PATCH'])
@permission_classes([IsManagerOrAbove])
def product_stock_update(request, pk):
    tenant = getattr(request.user, 'tenant', None)
    qs = Product.objects.all()
    if tenant:
        qs = qs.filter(tenant=tenant)
    try:
        product = qs.get(pk=pk)
    except Product.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    s = ProductStockUpdateSerializer(product, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(ProductSerializer(product).data)


# ── Products: CSV import / export ─────────────────────────────────────────────

CSV_EXPORT_COLUMNS = ['name', 'barcode', 'sku', 'price', 'cost', 'stock', 'reorder', 'category_name']


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def products_export(request):
    """
    GET /api/products/export/

    Streams a CSV of every product belonging to the caller's tenant.
    Columns: name, barcode, sku, price, cost, stock, reorder, category_name.
    """
    tenant = getattr(request.user, 'tenant', None)
    qs = Product.objects.select_related('category').all()
    if tenant:
        qs = qs.filter(tenant=tenant)
    qs = qs.order_by('name')

    filename = f'products-{timezone.now():%Y%m%d-%H%M%S}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # BOM so Excel opens UTF-8 correctly

    writer = csv.writer(response)
    writer.writerow(CSV_EXPORT_COLUMNS)
    for p in qs.iterator(chunk_size=500):
        writer.writerow([
            p.name,
            p.barcode,
            p.sku,
            p.price,
            p.cost,
            p.stock,
            p.reorder,
            p.category.name if p.category else '',
        ])
    return response


def _import_row(tenant, row, category_cache):
    """
    Upsert one CSV row into Product.

    Returns 'created' or 'updated' on success.
    Raises ValueError with a human-readable message on bad data.
    On update: only price, cost, stock are refreshed (per spec).
    """
    name    = (row.get('name')    or '').strip()
    barcode = (row.get('barcode') or '').strip()
    sku     = (row.get('sku')     or '').strip()

    if not name:
        raise ValueError('Missing product name')
    if not barcode:
        raise ValueError('Missing barcode')

    try:
        price = Decimal(str(row.get('price') or '0').strip())
        cost  = Decimal(str(row.get('cost')  or '0').strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid price or cost — must be a decimal number')

    # Accept "50" and "50.0" as 50; reject "50.5".
    try:
        stock_dec   = Decimal(str(row.get('stock')   or '0').strip())
        reorder_dec = Decimal(str(row.get('reorder') or '10').strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Invalid stock or reorder — must be a number')
    if stock_dec != stock_dec.to_integral_value() or reorder_dec != reorder_dec.to_integral_value():
        raise ValueError('stock and reorder must be whole numbers (e.g. 50, not 50.5)')
    stock   = int(stock_dec)
    reorder = int(reorder_dec)

    if price < 0 or cost < 0 or stock < 0 or reorder < 0:
        raise ValueError('Numeric fields must not be negative')

    cat_name = (row.get('category_name') or '').strip()
    category = None
    if cat_name:
        # Cache to avoid re-querying for repeated category names in the same import
        key = cat_name.lower()
        category = category_cache.get(key)
        if category is None:
            category, _ = Category.objects.get_or_create(tenant=tenant, name=cat_name)
            category_cache[key] = category

    existing = Product.objects.filter(tenant=tenant, barcode=barcode).first()
    if existing:
        # Sprint 3 Batch 3: `cost` is no longer a direct field write on an
        # existing product (see ProductSerializer.update()). A CSV row that
        # raises `stock` is treated the same as a positive physical count —
        # its `cost` column blends into the average via the same audited
        # path stock_adjustment uses. A row that doesn't raise stock (or
        # lowers it) carries no quantity basis to blend against, so its
        # `cost` column is ignored — the average stays whatever AVCO already
        # computed, matching the golden rule (no arbitrary cost override).
        stock_diff = stock - existing.stock
        if stock_diff > 0:
            costing.update_cost_from_adjustment(
                product=existing, qty=Decimal(stock_diff), adjustment_cost=cost,
                source_document_type='csv_import', note='CSV import upsert',
            )
        existing.price = price
        existing.stock = stock
        existing.save(update_fields=['price', 'stock', 'updated_at'])
        return 'updated'

    new_product = Product.objects.create(
        tenant   = tenant,
        barcode  = barcode,
        sku      = sku or barcode,
        name     = name,
        price    = price,
        cost     = cost,
        stock    = stock,
        reorder  = reorder,
        category = category,
    )
    costing.initialize_inventory_cost(product=new_product, opening_cost=cost)
    return 'created'


@api_view(['POST'])
@permission_classes([IsManagerOrAbove])
def products_import(request):
    """
    POST /api/products/import/   (multipart/form-data, field name: "file")

    Bulk-upsert products from a CSV. Each row is wrapped in its own savepoint,
    so a bad row never poisons the rest of the batch.
    """
    tenant = getattr(request.user, 'tenant', None)
    if not tenant:
        return Response(
            {'detail': 'User has no tenant.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    upload = request.FILES.get('file')
    if not upload:
        return Response(
            {'detail': 'No file provided. Send multipart/form-data with a "file" field.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        text = upload.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        return Response(
            {'detail': 'File must be UTF-8 encoded.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reader   = csv.DictReader(io.StringIO(text))
    headers  = {(h or '').strip() for h in (reader.fieldnames or [])}
    required = {'name', 'barcode'}
    missing  = required - headers
    if missing:
        return Response(
            {'detail': f'Missing required column(s): {sorted(missing)}. '
                       f'Required headers: {sorted(required)}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    total = created = updated = 0
    errors = []
    category_cache = {}

    for line_no, row in enumerate(reader, start=2):  # row 1 is the header
        total += 1
        try:
            with transaction.atomic():
                outcome = _import_row(tenant, row, category_cache)
            if outcome == 'created':
                created += 1
            else:
                updated += 1
        except ValueError as exc:
            errors.append({'row': line_no, 'error': str(exc)})
        except Exception as exc:
            errors.append({'row': line_no, 'error': f'Unexpected error: {exc}'})

    return Response(
        {
            'total_rows': total,
            'created':    created,
            'updated':    updated,
            'errors':     errors,
        },
        status=status.HTTP_200_OK,
    )


# ── Inventory batches ─────────────────────────────────────────────────────────

class ProductStockMovementListView(APIView):
    """GET /api/products/{pk}/stock-movements/ — per-product stock statement.

    Returns the summary envelope (opening_quantity, totals, net_change,
    closing_quantity, filters, date range) plus the row list — same
    shape as the financial statement endpoints introduced in the
    balance_before hardening slice. Honors the standard filter set:
    branch / movement_type / source_document_type / source_document_id /
    actor_user / date_from / date_to.
    """

    permission_classes = [IsManagerOrAbove]
    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        from pos.services import stock_movements as svc
        from accounts.models import Branch as _Branch
        from accounts.models import User as _User

        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            return Response(
                {'detail': 'User is not associated with a tenant.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        product = Product.objects.filter(tenant=tenant, pk=pk).first()
        if product is None:
            return Response(
                {'detail': 'Product not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        params = request.query_params

        branch = None
        if branch_id := params.get('branch'):
            branch = _Branch.objects.filter(tenant=tenant, pk=branch_id).first()
            if branch is None:
                return Response(
                    {'detail': 'Branch not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        actor_user = None
        if actor_user_id := params.get('actor_user'):
            actor_user = _User.objects.filter(tenant=tenant, pk=actor_user_id).first()
            if actor_user is None:
                return Response(
                    {'detail': 'User not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            source_document_id = (
                int(params['source_document_id'])
                if params.get('source_document_id') else None
            )
        except (TypeError, ValueError):
            return Response(
                {'detail': 'source_document_id must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = svc.get_product_stock_statement_summary(
            product,
            branch=branch,
            movement_type=params.get('movement_type') or None,
            source_document_type=params.get('source_document_type') or None,
            source_document_id=source_document_id,
            actor_user=actor_user,
            # Accept both `occurred_from`/`occurred_to` (legacy) and
            # `date_from`/`date_to` (v3.6 statement-contract name).
            occurred_from=params.get('occurred_from') or params.get('date_from') or None,
            occurred_to=params.get('occurred_to')   or params.get('date_to')   or None,
        )
        return Response(_serialize_stock_statement_summary(summary, request=request))


_QTY_QUANT = Decimal('0.001')


def _serialize_stock_statement_summary(summary, *, request):
    """Convert service-layer summary into JSON-ready body.

    Quantities are quantized to 3 decimal places so the response shape
    stays stable for the frontend whether totals are zero ('0.000') or
    have fractions ('12.345'). Datetimes render ISO-8601. The queryset
    is rendered through `StockMovementSerializer` with request context
    so per-tenant FK filtering still applies.
    """
    def _qty(v):
        if v is None:
            return None
        return f'{Decimal(v).quantize(_QTY_QUANT):.3f}'

    def _dt(v):
        if v is None:
            return None
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return str(v)

    return {
        'opening_quantity': _qty(summary['opening_quantity']),
        'total_in':         _qty(summary['total_in']),
        'total_out':        _qty(summary['total_out']),
        'net_change':       _qty(summary['net_change']),
        'closing_quantity': _qty(summary['closing_quantity']),
        'date_from':        _dt(summary['date_from']),
        'date_to':          _dt(summary['date_to']),
        'filters':          summary['filters'],
        'movements':        StockMovementSerializer(
            summary['movements'], many=True, context={'request': request},
        ).data,
    }


class ProductStockBalanceView(generics.GenericAPIView):
    """GET /api/products/{pk}/stock-balance/ — ledger-derived balance.

    Computed from StockMovement (in − out) so reports never trust the
    cached `Product.stock` value. Pass `?branch=<id>` for a per-branch
    balance.
    """

    permission_classes = [IsManagerOrAbove]

    def get(self, request, pk):
        from pos.services import stock_movements as svc

        tenant = getattr(request.user, 'tenant', None)
        product = Product.objects.filter(tenant=tenant, pk=pk).first()
        if product is None:
            return Response(
                {'detail': 'Product not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        branch_id = request.query_params.get('branch')
        branch = None
        if branch_id:
            from accounts.models import Branch as _Branch
            branch = _Branch.objects.filter(tenant=tenant, pk=branch_id).first()
            if branch is None:
                return Response(
                    {'detail': 'Branch not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        balance = svc.get_product_stock_balance(product, branch=branch)
        return Response({
            'product_id':    product.id,
            'product_name':  product.name,
            'branch_id':     branch.id if branch else None,
            'cached_stock':  str(product.stock),
            'ledger_stock':  str(balance),
        })


class StockMovementListCreateView(TenantMixin, generics.ListCreateAPIView):
    """
    GET  /api/stock-movements/?product_id=<id>
    POST /api/stock-movements/   (creates a movement and applies stock delta)

    The frontend uses this to render a per-product audit trail and to record
    stock receipts ("Receive Stock") without going through the heavier
    PurchaseReceipt flow.
    """

    queryset           = StockMovement.objects.select_related('product').all()
    serializer_class   = StockMovementSerializer
    permission_classes = [IsManagerOrAbove]
    filterset_class    = StockMovementFilter
    ordering_fields    = ['created_at']
    ordering           = ['-created_at']

    def get_queryset(self):
        # Honour the legacy `product=<id>` alias the StockMovementsModal sends.
        qs = super().get_queryset()
        product_alias = self.request.query_params.get('product')
        if product_alias and 'product_id' not in self.request.query_params:
            qs = qs.filter(product_id=product_alias)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class InventoryBatchListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset           = InventoryBatch.objects.select_related('product').all()
    serializer_class   = InventoryBatchSerializer
    search_fields      = ['batch_number', 'product__name']
    ordering_fields    = ['expiry_date', 'received_at']
    ordering           = ['expiry_date']
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs


class InventoryBatchDetailView(TenantMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset           = InventoryBatch.objects.select_related('product').all()
    serializer_class   = InventoryBatchSerializer
    permission_classes = [IsManagerOrAbove]


# ── Inventory actions ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsManagerOrAbove])
def purchase_receipt(request):
    tenant = getattr(request.user, 'tenant', None)
    if not tenant:
        return Response({'detail': 'User has no tenant.'}, status=status.HTTP_400_BAD_REQUEST)

    s = PurchaseReceiptSerializer(data=request.data, context={'request': request})
    s.is_valid(raise_exception=True)
    d = s.validated_data

    product      = d['product']
    qty          = d['qty']
    batch_number = d.get('batch_number') or f'AUTO-{timezone.now():%Y%m%d%H%M%S}'

    batch = InventoryBatch.objects.create(
        tenant             = tenant,
        product            = product,
        batch_number       = batch_number,
        remaining_quantity = qty,
        expiry_date        = d.get('expiry_date'),
        cost_price         = d.get('cost_price'),
    )

    Product.objects.filter(pk=product.pk).update(stock=F('stock') + qty)
    product.refresh_from_db(fields=['stock'])

    StockMovement.objects.create(
        tenant        = tenant,
        product       = product,
        qty           = qty,
        movement_type = StockMovement.MovementType.PURCHASE_IN,
        note          = f'Purchase receipt — batch {batch_number}',
    )

    return Response(
        {'batch': InventoryBatchSerializer(batch).data, 'product_stock': product.stock},
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsManagerOrAbove])
def stock_adjustment(request):
    tenant = getattr(request.user, 'tenant', None)
    if not tenant:
        return Response({'detail': 'User has no tenant.'}, status=status.HTTP_400_BAD_REQUEST)

    s = StockAdjustmentSerializer(data=request.data, context={'request': request})
    s.is_valid(raise_exception=True)
    d = s.validated_data

    product_ref = d['product']
    actual_qty  = d['actual_qty']
    reason      = d['reason']
    unit_cost   = d.get('unit_cost')

    with transaction.atomic():
        # Hotfix Pack: lock BEFORE reading current stock. Reading
        # `previous_stock` off the unlocked reference the serializer
        # resolved (as this view used to) left a lost-update race — two
        # concurrent adjustments on the same product could both read the
        # same stale value, compute their own `diff` against it, and the
        # second writer's blind `.update(stock=actual_qty)` would silently
        # clobber whatever the first one had just written. Locking first
        # closes that window: the second request blocks here until the
        # first commits, then reads the real post-first-adjustment stock.
        locked = Product.objects.select_for_update().get(pk=product_ref.pk)
        previous_stock = locked.stock
        diff           = actual_qty - previous_stock

        # A positive count with a known cost blends into the average exactly
        # like a purchase receipt (the golden rule's second AVCO-updating
        # event) — computed here, BEFORE Product.stock moves, so the blend
        # uses previous_stock (now guaranteed fresh, not stale). Shrinkage/
        # unchanged counts, or a positive count with no unit_cost given,
        # never touch the average — they consume it as-is.
        if diff > 0 and unit_cost is not None:
            costing.update_cost_from_adjustment(
                product=locked, qty=diff, adjustment_cost=unit_cost,
                source_document_type='stock_adjustment', actor_user=request.user,
                note=reason,
            )

        Product.objects.filter(pk=locked.pk).update(stock=actual_qty)
        locked.refresh_from_db(fields=['stock', 'cost'])

        # Hotfix Pack: explicit direction instead of the ambiguous legacy
        # `ADJUSTMENT` value (see MovementType docstring) — every reader
        # (quantity_in/out, get_product_stock_balance, statement
        # summaries) now classifies this row correctly with no guessing.
        # quantity_before/after are populated too, matching the hardened-
        # ledger convention every other write path in this module follows
        # (this endpoint used to be the one exception, leaving these NULL).
        movement_type = (
            StockMovement.MovementType.ADJUSTMENT_IN if diff >= 0
            else StockMovement.MovementType.ADJUSTMENT_OUT
        )
        StockMovement.objects.create(
            tenant           = tenant,
            product          = locked,
            qty              = diff,
            movement_type    = movement_type,
            quantity_before  = previous_stock,
            quantity_after   = locked.stock,
            actor_user       = request.user,
            note             = reason,
        )

    return Response({
        'product_id':     locked.pk,
        'product_name':   locked.name,
        'previous_stock': previous_stock,
        'new_stock':      locked.stock,
        'difference':     diff,
        'unit_cost':      str(unit_cost) if unit_cost is not None else None,
    })


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def inventory_alerts(request):
    tenant = getattr(request.user, 'tenant', None)
    qs = Product.objects.filter(active=True, stock__lt=F('reorder'))
    if tenant:
        qs = qs.filter(tenant=tenant)

    results = [
        {
            'product_id':    p.pk,
            'name':          p.name,
            'barcode':       p.barcode,
            'current_stock': p.stock,
            'reorder_point': p.reorder,
            'shortfall':     p.reorder - p.stock,
        }
        for p in qs.order_by('stock')
    ]

    return Response({'count': len(results), 'results': results})


# ── Sales ─────────────────────────────────────────────────────────────────────

class SaleListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset           = Sale.objects.select_related('cashier', 'branch', 'terminal').prefetch_related('items')
    filterset_class    = SaleFilter
    search_fields      = ['id', 'branch__name', 'terminal__name']
    ordering_fields    = ['created_at', 'total']
    ordering           = ['-created_at']
    permission_classes = [IsCashierOrAbove]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SaleSerializer
        return SaleListSerializer

    def get_queryset(self):
        # TenantMixin scopes by tenant; cashiers see only their own rows.
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, 'role', None) == 'Cashier':
            qs = qs.filter(cashier=user)
        return qs

    def perform_create(self, serializer):
        user   = self.request.user
        tenant = getattr(user, 'tenant', None)
        serializer.save(
            tenant   = tenant,
            cashier  = user,
            branch   = user.branch,
            terminal = user.terminal,
        )

    def create(self, request, *args, **kwargs):
        # Sprint 1 Slice 2: optional-but-honored Idempotency-Key, wired exactly
        # like PurchaseInvoiceListCreateView. No header → process normally (the
        # current frontend doesn't send one; making it mandatory is a later gate).
        tenant = self._tenant()
        key = (request.headers.get('Idempotency-Key') or '').strip()

        look = idempotency.lookup(
            tenant=tenant, key=key, payload=request.data,
            method=request.method, path=request.path, user=request.user,
        )
        if look.replay:
            return Response(look.body, status=look.status)
        if look.conflict:
            return Response(
                {'error': {
                    'code': 'IDEMPOTENCY_CONFLICT',
                    'detail': 'Idempotency-Key reused with a different payload.',
                }},
                status=status.HTTP_409_CONFLICT,
            )

        response = super().create(request, *args, **kwargs)

        idempotency.save(
            tenant=tenant, key=key, payload=request.data,
            method=request.method, path=request.path,
            response_status=response.status_code, response_body=response.data,
            user=request.user,
        )
        return response


@api_view(['GET'])
@permission_classes([IsCashierOrAbove])
def sales_export(request):
    """
    GET /api/sales/export/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

    CSV export of sales for the calling tenant, applying the same
    `start_date` / `end_date` filters as the list endpoint. Date params are
    inclusive on both ends. Returns text/csv with a download filename.
    """
    import datetime

    user   = request.user
    tenant = getattr(user, 'tenant', None)
    qs = (
        Sale.objects
        .select_related('cashier')
        .prefetch_related('items')
        .order_by('-created_at')
    )
    if tenant:
        qs = qs.filter(tenant=tenant)
    # Cashiers may only export their own sales.
    if getattr(user, 'role', None) == 'Cashier':
        qs = qs.filter(cashier=user)

    start_param = request.query_params.get('start_date')
    end_param   = request.query_params.get('end_date')

    def _parse(name, value):
        try:
            return datetime.date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(f'Invalid {name}: expected YYYY-MM-DD.')

    try:
        if start_param:
            qs = qs.filter(created_at__date__gte=_parse('start_date', start_param))
        if end_param:
            qs = qs.filter(created_at__date__lte=_parse('end_date', end_param))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    qs = qs.annotate(_item_count=Count('items'))

    filename = 'sales_export.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # UTF-8 BOM so Excel opens Arabic columns correctly

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Date', 'Cashier', 'Method',
        'Items Count', 'Subtotal', 'Tax', 'Total', 'Status',
    ])
    for s in qs.iterator(chunk_size=500):
        short_id = (str(s.sale_uuid)[-8:] if s.sale_uuid else str(s.pk))
        cashier  = ''
        if s.cashier_id:
            cashier = s.cashier.get_full_name() or s.cashier.username
        writer.writerow([
            short_id,
            timezone.localtime(s.created_at).strftime('%Y-%m-%d %H:%M:%S'),
            cashier,
            s.method,
            s._item_count,
            s.subtotal,
            s.tax_amount,
            s.total,
            s.status,
        ])
    return response


@api_view(['GET'])
@permission_classes([IsCashierOrAbove])
def sale_receipt(request, sale_uuid=None, pk=None):
    """
    GET /api/sales/<uuid|pk>/receipt/

    Returns the structured receipt payload — system-filled fields under
    `auto`, tenant-configured text under `config`, lines + totals. The
    frontend renders the printed bill from this without baking in any
    policy text.
    """
    tenant = getattr(request.user, 'tenant', None)
    qs = (
        Sale.objects
        .select_related('cashier', 'branch', 'terminal', 'tenant', 'payment')
        .prefetch_related('items')
    )
    if tenant:
        qs = qs.filter(tenant=tenant)
    if getattr(request.user, 'role', None) == 'Cashier':
        qs = qs.filter(cashier=request.user)

    if sale_uuid:
        sale = get_object_or_404(qs, sale_uuid=sale_uuid)
    else:
        sale = get_object_or_404(qs, pk=pk)
    return Response(ReceiptSerializer(sale).data)


class SaleDetailView(TenantMixin, generics.RetrieveAPIView):
    queryset           = Sale.objects.select_related('cashier', 'branch', 'terminal').prefetch_related('items__product')
    serializer_class   = SaleSerializer
    permission_classes = [IsCashierOrAbove]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, 'role', None) == 'Cashier':
            qs = qs.filter(cashier=user)
        return qs

    def get_object(self):
        qs = self.get_queryset()
        if 'sale_uuid' in self.kwargs:
            obj = get_object_or_404(qs, sale_uuid=self.kwargs['sale_uuid'])
        else:
            obj = get_object_or_404(qs, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, obj)
        return obj


@api_view(['POST'])
@permission_classes([IsCashierOrAbove])
def void_sale(request, pk=None, sale_uuid=None):
    """
    POST /api/sales/<id|uuid>/void/

    Permissions:
      - Manager/Admin/Owner can void any sale within their tenant.
      - Cashier can void only their own sales.

    Already-voided sales return 400. The sale row is locked
    (`select_for_update`) so a concurrent double-void cannot double-reverse.

    Gate A (GA-7) — the void is financially correct, not just inventory-correct:
      * Inventory is restored: each line's product stock is incremented and a
        `RETURN_IN` StockMovement is logged so the audit trail remains intact.
      * Every FinancialAccountMovement the sale posted (cash/card/wallet) is
        reversed with a compensating SALES_RETURN_OUT credit on the same
        account. Original rows are never deleted (compensating-document
        pattern, R-C).
      * Every CustomerARMovement the sale posted (credit sales) is reversed
        with a compensating SALES_RETURN credit on the customer.
      * A pre-gate legacy sale with no financial movement reverses stock only
        and flags `legacy_no_financial_movement` in the response.
      * Body may carry an OPTIONAL `reason` string; actor/timestamp/reason and
        the reversal references are recorded in an AuditLog entry.

    Supports the optional Idempotency-Key header: a replayed void returns the
    original response without re-processing.
    """
    user   = request.user
    tenant = getattr(user, 'tenant', None)

    # Optional-but-honored idempotency (same pattern as sale/purchase create).
    key = (request.headers.get('Idempotency-Key') or '').strip()
    look = idempotency.lookup(
        tenant=tenant, key=key, payload=request.data,
        method=request.method, path=request.path, user=user,
    )
    if look.replay:
        return Response(look.body, status=look.status)
    if look.conflict:
        return Response(
            {'error': {
                'code': 'IDEMPOTENCY_CONFLICT',
                'detail': 'Idempotency-Key reused with a different payload.',
            }},
            status=status.HTTP_409_CONFLICT,
        )

    reason = str(request.data.get('reason') or '').strip()

    from pos.services import stock_movements as stock_svc

    try:
        with transaction.atomic():
            # Row-lock the sale so two concurrent voids serialize; the loser
            # re-reads status=VOIDED and returns 400 instead of re-reversing.
            # `of=('self',)` locks only the Sale row (cashier is a nullable
            # join, which FOR UPDATE cannot lock on PostgreSQL).
            qs = Sale.objects.select_for_update(of=('self',)).select_related('cashier')
            if tenant:
                qs = qs.filter(tenant=tenant)

            if sale_uuid is not None:
                sale = get_object_or_404(qs, sale_uuid=sale_uuid)
            else:
                sale = get_object_or_404(qs, pk=pk)

            if getattr(user, 'role', None) == 'Cashier' and sale.cashier_id != user.id:
                return Response(
                    {'detail': 'Cashiers can only void their own sales.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if sale.status == Sale.Status.VOIDED:
                return Response(
                    {'detail': 'Sale is already voided.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if sale.status != Sale.Status.COMPLETED:
                return Response(
                    {'detail': 'Only completed sales can be voided.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sale.status = Sale.Status.VOIDED
            sale.save(update_fields=['status', 'updated_at'])

            # ── Stock reversal ────────────────────────────────────────────
            # Restore product stock + record the reversing movement. Keep qty
            # as Decimal so weighted items (e.g., 0.5 kg) round-trip without
            # truncating to zero.
            from recipes.services import costing as recipes_costing_svc

            for item in sale.items.select_related('product', 'warehouse').all():
                if not item.product_id:
                    continue
                if recipes_costing_svc.is_recipe_eligible(item.product):
                    # Sprint 5 Batch 5 hotfix (review point 5): a recipe
                    # product was never itself decremented at sale time —
                    # only its ingredients were, via RECIPE_CONSUME. Bumping
                    # Product.stock on the recipe product here (as the
                    # legacy path below does) would be meaningless, and
                    # skipping ingredient reversal entirely would silently
                    # leak stock forever on every recipe-sale void. The
                    # actual reversal happens once, below, from the
                    # RECIPE_CONSUME ledger — not recomputed from the
                    # recipe/modifier definitions (those may have changed
                    # since the sale; only the frozen movements are trusted).
                    continue
                qty = item.qty
                if qty > 0:
                    Product.objects.filter(pk=item.product_id).update(
                        stock=F('stock') + qty,
                    )
                    # Restore the cached per-warehouse balance to the same
                    # warehouse the goods originally left from (no-op when the
                    # line has no warehouse — legacy / unconfigured sale).
                    stock_svc.apply_warehouse_delta(
                        product=item.product, warehouse=item.warehouse, delta=qty,
                    )
                StockMovement.objects.create(
                    tenant        = tenant,
                    product_id    = item.product_id,
                    warehouse     = item.warehouse,
                    qty           = qty,
                    movement_type = StockMovement.MovementType.RETURN_IN,
                    sale          = sale,
                    source_document_type = 'sale_void',
                    source_document_id   = sale.id,
                    actor_user    = user,
                    note          = f'Void of sale {sale.sale_uuid}',
                )

            # ── Recipe-ingredient stock reversal (Sprint 5 hotfix) ─────────
            # Reverses every RECIPE_CONSUME movement this sale posted — read
            # straight from the StockMovement ledger (the frozen record of
            # what actually left stock), never from a fresh recipe/modifier
            # computation. This is what makes a recipe-product sale's void
            # correct: the ingredients that were actually depleted are the
            # ones restored, at the same warehouse they left from.
            recipe_consume_moves = StockMovement.objects.filter(
                tenant=tenant, sale=sale,
                movement_type=StockMovement.MovementType.RECIPE_CONSUME,
            ).select_related('product', 'warehouse')
            for mv in recipe_consume_moves:
                qty = -mv.qty  # RECIPE_CONSUME rows are stored negative.
                if qty > 0 and mv.product_id:
                    Product.objects.filter(pk=mv.product_id).update(
                        stock=F('stock') + qty,
                    )
                    stock_svc.apply_warehouse_delta(
                        product=mv.product, warehouse=mv.warehouse, delta=qty,
                    )
                StockMovement.objects.create(
                    tenant        = tenant,
                    product_id    = mv.product_id,
                    warehouse     = mv.warehouse,
                    qty           = qty,
                    movement_type = StockMovement.MovementType.RETURN_IN,
                    sale          = sale,
                    source_document_type = 'sale_void',
                    source_document_id   = sale.id,
                    actor_user    = user,
                    note          = f'Void of sale {sale.sale_uuid} — recipe ingredient reversal',
                )

            # ── Financial reversal (GA-7) ─────────────────────────────────
            # Compensating rows only — the original movements stay untouched.
            notes = f'Void of sale {sale.sale_uuid}'
            finance_reversals = []
            for mv in FinancialAccountMovement.objects.filter(
                tenant=tenant, source_document_type='sale',
                source_document_id=sale.id, debit__gt=0,
            ).select_related('account'):
                rev = fa.record_account_credit(
                    account=mv.account,
                    amount=mv.debit,
                    movement_type=fa.MovementType.SALES_RETURN_OUT,
                    branch=sale.branch,
                    source_document_type='sale_void',
                    source_document_id=sale.id,
                    actor_user=user,
                    notes=notes,
                )
                finance_reversals.append({
                    'reversal_movement_id': rev.id,
                    'original_movement_id': mv.id,
                    'account_id': mv.account_id,
                    'amount': str(mv.debit),
                })

            ar_reversals = []
            for mv in CustomerARMovement.objects.filter(
                tenant=tenant, source_document_type='sale',
                source_document_id=sale.id, debit__gt=0,
            ).select_related('customer'):
                rev = ar.record_customer_ar_credit(
                    customer=mv.customer,
                    amount=mv.debit,
                    movement_type=ar.MovementType.SALES_RETURN,
                    branch=sale.branch,
                    source_document_type='sale_void',
                    source_document_id=sale.id,
                    actor_user=user,
                    notes=notes,
                )
                ar_reversals.append({
                    'reversal_movement_id': rev.id,
                    'original_movement_id': mv.id,
                    'customer_id': mv.customer_id,
                    'amount': str(mv.debit),
                })

            legacy_no_financial_movement = (
                not finance_reversals and not ar_reversals
            )

            AuditLog.log_change(
                tenant=tenant, user=user, action=AuditLog.Action.VOID,
                model_name='sale', object_id=sale.id,
                old_values={'status': Sale.Status.COMPLETED},
                new_values={
                    'status': Sale.Status.VOIDED,
                    'finance_reversals': finance_reversals,
                    'ar_reversals': ar_reversals,
                    'legacy_no_financial_movement': legacy_no_financial_movement,
                },
                request=request, reason=reason,
            )
    except (fa.AccountMovementError, ar.CustomerARError) as exc:
        # Reversal rule violation → the atomic block rolled everything back
        # (status flip, stock restore, partial reversals). Surface as 400.
        return Response(
            {'detail': str(exc), 'code': 'void_reversal_failed'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    sale.refresh_from_db()
    body = SaleSerializer(sale).data
    body['void'] = {
        'reason': reason,
        'finance_reversals': finance_reversals,
        'ar_reversals': ar_reversals,
        'legacy_no_financial_movement': legacy_no_financial_movement,
    }

    idempotency.save(
        tenant=tenant, key=key, payload=request.data,
        method=request.method, path=request.path,
        response_status=status.HTTP_200_OK, response_body=body,
        user=user,
    )
    return Response(body)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def dashboard_summary(request):
    """
    GET /api/dashboard/summary/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

    All KPIs are aggregated over the inclusive [start_date, end_date] window
    using `created_at__date__range`. When the params are omitted the window
    defaults to today only. Tenant-scoped; Manager/Admin/Owner only.

    Backwards-compatible: still emits the legacy `today / this_week /
    this_month / payment_methods` shape so existing callers don't break.
    """
    import datetime

    tenant = getattr(request.user, 'tenant', None)
    today  = timezone.localdate()

    def _parse(name, value, fallback):
        if not value:
            return fallback
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'Invalid {name}: expected YYYY-MM-DD.')

    try:
        start = _parse('start_date', request.query_params.get('start_date'), today)
        end   = _parse('end_date',   request.query_params.get('end_date'),   today)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Safety: if the caller sent an inverted range (start strictly after end),
    # swap before applying `created_at__date__range` so the ORM never sees an
    # impossible window. Friendlier than returning 400 for what's clearly a
    # picker glitch.
    if start > end:
        start, end = end, start

    completed = Sale.objects.filter(status=Sale.Status.COMPLETED)
    products  = Product.objects.filter(active=True)
    if tenant:
        completed = completed.filter(tenant=tenant)
        products  = products.filter(tenant=tenant)

    # Sprint 4 Batch 2: optional branch scoping. Cost/COGS figures need no
    # special handling — SaleItem.unit_cost is a per-line snapshot already
    # independent of which branch sold it (D-09 keeps InventoryCost itself
    # tenant-wide), so filtering the base Sale queryset by branch is enough.
    branch_id = request.query_params.get('branch_id')
    if branch_id:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid branch_id: expected an integer.'}, status=status.HTTP_400_BAD_REQUEST)
        get_object_or_404(Branch, pk=branch_id, tenant=tenant) if tenant else get_object_or_404(Branch, pk=branch_id)
        completed = completed.filter(branch_id=branch_id)

    window = completed.filter(created_at__date__range=(start, end))

    # ── Window KPIs ──────────────────────────────────────────────────────────
    agg = window.aggregate(
        revenue=Sum('total'),
        tax_total=Sum('tax_amount'),
        transactions=Count('id'),
        avg_basket=Avg('total'),
    )
    # `SaleItem.qty`/`unit_cost` are already base-unit/2dp-cost-denominated
    # regardless of which unit a line was sold in (Sprint 2 Batch 5a
    # converts server-side at sale time) — no ProductUnit join needed.
    window_items = SaleItem.objects.filter(sale__in=window)

    def _cogs_sum():
        # A fresh ExpressionWrapper per call — safe to call this more than
        # once per queryset chain (see the alias note below for why a
        # shared instance isn't actually the issue here).
        return Sum(ExpressionWrapper(
            F('unit_cost') * F('qty'), output_field=DecimalField(max_digits=16, decimal_places=5),
        ))

    # NOTE: the aggregate() output alias must NOT be 'qty' — Django adds
    # every kwarg as an annotation before aggregating, so an alias named
    # 'qty' shadows the real `SaleItem.qty` field, and cogs's F('qty')
    # reference then resolves to that annotation (itself a Sum, i.e. an
    # aggregate) instead of the column — raising "'qty' is an aggregate".
    item_agg   = window_items.aggregate(total_qty=Sum('qty'), cogs=_cogs_sum())
    items_sold = float(item_agg['total_qty'] or 0)

    revenue      = float(agg['revenue'] or 0)
    transactions = agg['transactions'] or 0
    avg_basket   = round(float(agg['avg_basket'] or 0), 2)

    # ── COGS / gross profit / margin (Sprint 3 Batch 4) ───────────────────────
    # net_revenue = tax-exclusive, discount-inclusive revenue. `Sale` has no
    # stored discount_amount field — `total = subtotal + tax_amount -
    # discount_amount`, so `total - tax_amount` algebraically recovers
    # `subtotal - discount_amount` without a new field. Matches
    # TARGET_BOUNDARIES.md's "net revenue" convention (menu price net of
    # VAT). R-L: these are "gross profit" figures — never "net profit",
    # which is reserved for a future GL-level figure after operating
    # expenses.
    net_revenue_decimal = costing.quantize_money(
        (agg['revenue'] or Decimal('0')) - (agg['tax_total'] or Decimal('0')),
    )
    cogs_decimal = costing.quantize_money(item_agg['cogs'] or 0)
    gross_profit_decimal = costing.quantize_money(net_revenue_decimal - cogs_decimal)
    gross_margin_pct = (
        round(float(gross_profit_decimal / net_revenue_decimal) * 100, 1)
        if net_revenue_decimal > 0 else 0.0
    )

    kpis = {
        'revenue':      revenue,
        'transactions': transactions,
        'avg_basket':   avg_basket,
        'items_sold':   items_sold,
        'net_revenue':       float(net_revenue_decimal),
        'cogs':              float(cogs_decimal),
        'gross_profit':      float(gross_profit_decimal),
        'gross_margin_pct':  gross_margin_pct,
        # Trends require a previous-window comparison — return zeros so the UI
        # can still render the delta line cleanly until that lands.
        'revenue_trend':      0.0,
        'transactions_trend': 0.0,
        'avg_basket_trend':   0.0,
        'items_sold_trend':   0.0,
    }

    # ── Top products (by revenue) within the window ──────────────────────────
    # Sprint 4 Batch 2: group by `product` id (not just the free-text
    # `product_name` snapshot) so the frontend can drill down to a real
    # product. SaleItem.product is SET_NULL — a since-deleted product has no
    # page to link to anyway, so it's excluded here rather than surfaced
    # with a dead link.
    top_products = []
    for row in (
        window_items
        .exclude(product__isnull=True)
        .values('product', 'product_name')
        .annotate(units_sold=Sum('qty'), revenue=Sum('line_total'), cogs=_cogs_sum())
        .order_by('-revenue')[:10]
    ):
        row_revenue = row['revenue'] or Decimal('0')
        row_cogs    = costing.quantize_money(row['cogs'] or 0)
        row_profit  = costing.quantize_money(row_revenue - row_cogs)
        top_products.append({
            'id':                row['product'],
            'name':              row['product_name'],
            'units_sold':        float(row['units_sold'] or 0),
            'revenue':           float(row_revenue),
            'cogs':              float(row_cogs),
            'gross_profit':      float(row_profit),
            'gross_margin_pct':  (
                round(float(row_profit / row_revenue) * 100, 1) if row_revenue > 0 else 0.0
            ),
        })

    # ── Payment methods within window ───────────────────────────────────────
    payment_methods = {}
    for method_val, method_label in Sale.Method.choices:
        r = window.filter(method=method_val).aggregate(
            count=Count('id'), total=Sum('total'),
        )
        total = float(r['total'] or 0)
        payment_methods[method_val] = {
            'label': method_label,
            'count': r['count'],
            'total': total,
            'pct':   round((total / revenue) * 100, 1) if revenue > 0 else 0,
        }

    # ── Low stock (current state, not date-bound) ────────────────────────────
    low_stock_qs = products.filter(stock__lte=F('reorder')).order_by('stock')
    low_stock = [
        {
            'id':            p.pk,
            'name':          p.name,
            'color':         p.color,
            'stock':         float(p.stock),
            'reorder_point': float(p.reorder),
            'unit':          p.unit,
        }
        for p in low_stock_qs[:20]
    ]
    low_stock_count = low_stock_qs.count()

    # ── Backwards-compatible blocks for older callers ────────────────────────
    def legacy_agg(qs):
        r = qs.aggregate(revenue=Sum('total'), count=Count('id'), avg=Avg('total'))
        return {
            'total': float(r['revenue'] or 0),
            'count': r['count'],
            'avg':   round(float(r['avg'] or 0), 2),
        }

    today_start = today
    week_start  = today - timedelta(days=7)
    month_start = today - timedelta(days=30)

    return Response({
        'range': {
            'start_date': start.isoformat(),
            'end_date':   end.isoformat(),
        },
        'kpis':            kpis,
        'top_products':    top_products,
        'payment_methods': payment_methods,
        'low_stock':       low_stock,
        'low_stock_count': low_stock_count,
        # ── Legacy fields (kept for the older dashboard endpoint consumers) ──
        'today':      legacy_agg(completed.filter(created_at__date=today_start)),
        'this_week':  legacy_agg(completed.filter(created_at__date__gte=week_start)),
        'this_month': legacy_agg(completed.filter(created_at__date__gte=month_start)),
    })


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def dashboard_trend(request):
    """
    GET /api/dashboard/trend/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&branch_id=

    Sprint 4 Batch 1: one row per calendar day across the window, for the
    Margin/COGS chart. Same window/branch semantics as `dashboard_summary`
    (required date range defaulting to today; optional tenant-scoped
    `branch_id`) but grouped by day instead of collapsed to one aggregate.
    Daily granularity only — no weekly/monthly downsampling this sprint; a
    year-long range is 365 points, acceptable for a line chart.
    """
    import datetime

    tenant = getattr(request.user, 'tenant', None)
    today  = timezone.localdate()

    def _parse(name, value, fallback):
        if not value:
            return fallback
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'Invalid {name}: expected YYYY-MM-DD.')

    try:
        start = _parse('start_date', request.query_params.get('start_date'), today)
        end   = _parse('end_date',   request.query_params.get('end_date'),   today)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if start > end:
        start, end = end, start

    completed = Sale.objects.filter(status=Sale.Status.COMPLETED)
    if tenant:
        completed = completed.filter(tenant=tenant)

    branch_id = request.query_params.get('branch_id')
    if branch_id:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid branch_id: expected an integer.'}, status=status.HTTP_400_BAD_REQUEST)
        get_object_or_404(Branch, pk=branch_id, tenant=tenant) if tenant else get_object_or_404(Branch, pk=branch_id)
        completed = completed.filter(branch_id=branch_id)

    window = completed.filter(created_at__date__range=(start, end))

    # Per-day revenue/tax, keyed by date.
    by_day_sale = {
        row['day']: row
        for row in (
            window
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(revenue=Sum('total'), tax_total=Sum('tax_amount'))
        )
    }
    # Per-day COGS, keyed by date — a separate query since it groups
    # SaleItem (via its sale FK), not Sale itself (same two-query shape
    # `dashboard_summary` already uses for its single-aggregate case).
    by_day_cogs = {
        row['day']: row['cogs'] or 0
        for row in (
            SaleItem.objects.filter(sale__in=window)
            .annotate(day=TruncDate('sale__created_at'))
            .values('day')
            .annotate(cogs=Sum(ExpressionWrapper(
                F('unit_cost') * F('qty'), output_field=DecimalField(max_digits=16, decimal_places=5),
            )))
        )
    }

    days = []
    cur = start
    one_day = datetime.timedelta(days=1)
    while cur <= end:
        row = by_day_sale.get(cur)
        net_revenue_decimal = costing.quantize_money(
            (row['revenue'] if row else Decimal('0')) - (row['tax_total'] if row else Decimal('0')),
        )
        cogs_decimal = costing.quantize_money(by_day_cogs.get(cur, 0))
        gross_profit_decimal = costing.quantize_money(net_revenue_decimal - cogs_decimal)
        gross_margin_pct = (
            round(float(gross_profit_decimal / net_revenue_decimal) * 100, 1)
            if net_revenue_decimal > 0 else 0.0
        )
        days.append({
            'date':              cur.isoformat(),
            'net_revenue':       float(net_revenue_decimal),
            'cogs':              float(cogs_decimal),
            'gross_profit':      float(gross_profit_decimal),
            'gross_margin_pct':  gross_margin_pct,
        })
        cur += one_day

    return Response({
        'range': {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'days':  days,
    })


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def dashboard_top_products(request):
    tenant = getattr(request.user, 'tenant', None)
    today  = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    qs = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__gte=today,
    )
    if tenant:
        qs = qs.filter(sale__tenant=tenant)

    # Sprint 4 Batch 2: same product-id fix as dashboard_summary's
    # top_products block — exclude SET_NULL'd deleted products rather than
    # surface a row with nothing to drill into.
    top = list(
        qs.exclude(product__isnull=True)
        .values('product', 'product_name')
        .annotate(qty_sold=Sum('qty'), revenue=Sum('line_total'))
        .order_by('-qty_sold')[:10]
    )
    for item in top:
        item['id']       = item.pop('product')
        item['qty_sold'] = float(item['qty_sold'])
        item['revenue']  = float(item['revenue'])

    return Response(top)


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def dashboard_low_stock(request):
    tenant = getattr(request.user, 'tenant', None)
    qs = Product.objects.filter(active=True, stock__lt=F('reorder'))
    if tenant:
        qs = qs.filter(tenant=tenant)

    results = [
        {
            'product_id':    p.pk,
            'name':          p.name,
            'barcode':       p.barcode,
            'category':      p.category.name if p.category else '',
            'current_stock': p.stock,
            'reorder_point': p.reorder,
            'shortfall':     p.reorder - p.stock,
        }
        for p in qs.select_related('category').order_by('stock')
    ]

    return Response({'count': len(results), 'results': results})


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def dashboard_daily_stats(request):
    import datetime

    tenant     = getattr(request.user, 'tenant', None)
    date_param = request.query_params.get('date')

    if date_param:
        try:
            parsed = datetime.date.fromisoformat(date_param)
        except ValueError:
            return Response(
                {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        day_start = timezone.make_aware(
            datetime.datetime(parsed.year, parsed.month, parsed.day)
        )
    else:
        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        parsed    = day_start.date()

    day_end = day_start + timedelta(days=1)

    qs = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__gte=day_start,
        created_at__lt=day_end,
    )
    if tenant:
        qs = qs.filter(tenant=tenant)

    agg = qs.aggregate(total_sales=Sum('total'), count=Count('id'), avg=Avg('total'))

    total_items = (
        SaleItem.objects
        .filter(sale__in=qs)
        .aggregate(qty=Sum('qty'))['qty'] or 0
    )

    return Response({
        'date':              parsed.isoformat(),
        'total_sales':       float(agg['total_sales'] or 0),
        'transaction_count': agg['count'],
        'avg_basket':        round(float(agg['avg'] or 0), 2),
        'total_items':       float(total_items),
    })


# ── Recipe / food-cost reporting (Sprint 5 Batch 6) ───────────────────────────
# Both views below are pure reads over data Batch 5 already writes — no new
# write-side code, matching the "reuse the COGS pipeline with zero write-side
# change" strategy `dashboard_summary`'s COGS/gross-profit figures already use
# for stock-item products (Sprint 3/4). Not GL-posted (R-L discipline
# unchanged): "gross profit"/"food cost", never "net profit".

def _parse_report_window(request, tenant):
    """Shared start/end/branch_id parsing for the two report views below —
    identical semantics to `dashboard_summary`'s own inline parsing (date
    range defaults to today, an inverted range is swapped, `branch_id` is
    tenant-scoped and 404s if unknown). Factored out only because both new
    views need it verbatim; raises `ValueError` on a bad param, which each
    caller turns into a 400."""
    import datetime

    today = timezone.localdate()

    def _parse(name, value, fallback):
        if not value:
            return fallback
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'Invalid {name}: expected YYYY-MM-DD.')

    start = _parse('start_date', request.query_params.get('start_date'), today)
    end   = _parse('end_date',   request.query_params.get('end_date'),   today)
    if start > end:
        start, end = end, start

    branch_id = request.query_params.get('branch_id')
    if branch_id:
        try:
            branch_id = int(branch_id)
        except (TypeError, ValueError):
            raise ValueError('Invalid branch_id: expected an integer.')
        get_object_or_404(Branch, pk=branch_id, tenant=tenant) if tenant else get_object_or_404(Branch, pk=branch_id)

    return start, end, branch_id


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def recipe_profitability(request):
    """
    GET /api/reports/recipe-profitability/?start_date=&end_date=&branch_id=&ordering=

    Per-(product, variant) food-cost/margin breakdown for RECIPE_PRODUCT
    sales in the window — the "best/worst margin" report from the owner's
    mock reports. `food_cost` reads the same `SaleItem.unit_cost` snapshot
    `SaleSerializer.create()` already writes for a recipe sale line (the
    branch-scoped recipe cost frozen at the moment of sale, Sprint 5 Batch
    5) — this view never recomputes a recipe's cost itself.

    `?ordering=` accepts `revenue`, `units_sold`, `gross_profit`,
    `gross_margin_pct`, or `food_cost_pct`, each with an optional `-`
    prefix for descending; defaults to `-revenue`. Grouped by
    `(product, product_name, variant, variant_name)` — the name snapshot
    fields, not a live join, so a row reflects the names as they were sold
    (same known limitation `dashboard_summary`'s `top_products` already
    has: a mid-window rename can split one logical product across two
    rows).
    """
    tenant = getattr(request.user, 'tenant', None)
    try:
        start, end, branch_id = _parse_report_window(request, tenant)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    items = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__range=(start, end),
        product__product_type=ProductType.RECIPE_PRODUCT,
    ).exclude(product__isnull=True)
    if tenant:
        items = items.filter(sale__tenant=tenant)
    if branch_id:
        items = items.filter(sale__branch_id=branch_id)

    def _cost_sum():
        return Sum(ExpressionWrapper(
            F('unit_cost') * F('qty'), output_field=DecimalField(max_digits=16, decimal_places=5),
        ))

    rows = []
    for row in (
        items
        # Explicit empty order_by() clears SaleItem's default `Meta.ordering
        # = ['id']` — left in place, Django would fold `id` into the GROUP
        # BY and defeat this aggregation entirely (same gotcha every other
        # `.values().annotate()` block in this file already works around).
        .values('product', 'product_name', 'variant', 'variant_name')
        .annotate(units_sold=Sum('qty'), revenue=Sum('line_total'), food_cost=_cost_sum())
        .order_by()
    ):
        revenue      = row['revenue'] or Decimal('0')
        food_cost    = costing.quantize_money(row['food_cost'] or 0)
        gross_profit = costing.quantize_money(revenue - food_cost)
        rows.append({
            'product_id':       row['product'],
            'product_name':     row['product_name'],
            'variant_id':       row['variant'],
            'variant_name':     row['variant_name'] or '',
            'units_sold':       float(row['units_sold'] or 0),
            'revenue':          float(revenue),
            'food_cost':        float(food_cost),
            'gross_profit':     float(gross_profit),
            'gross_margin_pct': (
                round(float(gross_profit / revenue) * 100, 1) if revenue > 0 else 0.0
            ),
            'food_cost_pct': (
                round(float(food_cost / revenue) * 100, 1) if revenue > 0 else 0.0
            ),
        })

    allowed_ordering = {
        'revenue', '-revenue', 'units_sold', '-units_sold',
        'gross_profit', '-gross_profit', 'gross_margin_pct', '-gross_margin_pct',
        'food_cost_pct', '-food_cost_pct',
    }
    ordering = request.query_params.get('ordering') or '-revenue'
    if ordering not in allowed_ordering:
        ordering = '-revenue'
    rows.sort(key=lambda r: r[ordering.lstrip('-')], reverse=ordering.startswith('-'))

    return Response({
        'range':   {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'results': rows,
    })


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def ingredient_consumption_report(request):
    """
    GET /api/reports/ingredient-consumption/?start_date=&end_date=&branch_id=&ordering=

    Per-ingredient consumption/cost breakdown, read directly from the
    `RECIPE_CONSUME` stock-movement ledger — the "most-consumed
    ingredients" report from the owner's mock reports. Reads the ledger
    (never recomputes from a live recipe definition), the same "the
    ledger is the source of truth" rule `pos.views.void_sale`'s own
    `RECIPE_CONSUME` reversal already follows.

    Unlike `recipe_profitability` above, a stock movement carries no cost
    snapshot of its own — `cost_consumed` is derived here from each
    movement's own `(product, branch)` branch-scoped `InventoryCost`
    (D-09), read fresh at request time, not the cost at the moment that
    particular unit was actually consumed. This is a live report, not an
    immutable audit snapshot like `SaleItemRecipeCostSnapshot`.

    `?ordering=` accepts `qty_consumed` or `cost_consumed`, each with an
    optional `-` prefix; defaults to `-cost_consumed`.
    """
    tenant = getattr(request.user, 'tenant', None)
    try:
        start, end, branch_id = _parse_report_window(request, tenant)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    movements = StockMovement.objects.filter(
        movement_type=StockMovement.MovementType.RECIPE_CONSUME,
        created_at__date__range=(start, end),
    ).exclude(product__isnull=True).select_related('product', 'branch')
    if tenant:
        movements = movements.filter(tenant=tenant)
    if branch_id:
        movements = movements.filter(branch_id=branch_id)

    # One InventoryCost lookup per distinct (product, branch) pair seen,
    # not one per movement row — the same small per-call cache pattern
    # `recipes.services.costing.compute_recipe_sale_lines` uses.
    unit_cost_cache = {}

    def _unit_cost(product, branch):
        key = (product.id, branch.id if branch else None)
        cost = unit_cost_cache.get(key)
        if cost is None:
            cost = costing.get_cost_for_sale(product, branch=branch)
            unit_cost_cache[key] = cost
        return cost

    # Raw (unrounded) accumulation per product, quantized to money once at
    # the end — the same "sum raw, round once" discipline this session's
    # snapshot-line rounding fix established, applied here for the same
    # reason: summing already-rounded per-movement costs could drift the
    # total on a component whose raw cost isn't already a clean 2dp value.
    totals = {}
    for mv in movements.iterator():
        qty_consumed = -mv.qty  # RECIPE_CONSUME rows are stored negative.
        if qty_consumed <= 0:
            continue
        unit_cost = _unit_cost(mv.product, mv.branch)
        entry = totals.setdefault(mv.product_id, {
            'product_name': mv.product.name,
            'qty_consumed': Decimal('0'),
            'raw_cost':     Decimal('0'),
        })
        entry['qty_consumed'] += qty_consumed
        entry['raw_cost']     += qty_consumed * unit_cost

    rows = [
        {
            'product_id':    product_id,
            'product_name':  data['product_name'],
            'qty_consumed':  float(data['qty_consumed']),
            'cost_consumed': float(costing.quantize_money(data['raw_cost'])),
        }
        for product_id, data in totals.items()
    ]

    allowed_ordering = {'qty_consumed', '-qty_consumed', 'cost_consumed', '-cost_consumed'}
    ordering = request.query_params.get('ordering') or '-cost_consumed'
    if ordering not in allowed_ordering:
        ordering = '-cost_consumed'
    rows.sort(key=lambda r: r[ordering.lstrip('-')], reverse=ordering.startswith('-'))

    return Response({
        'range':   {'start_date': start.isoformat(), 'end_date': end.isoformat()},
        'results': rows,
    })


# ── Dynamic Warehouses / Stores (Phase 1.5 foundation) ────────────────────────
# Backend foundation only. Manager+ writes, Cashier+ reads — mirrors the
# master-data convention used by ProductListCreateView / BranchV2*. Deactivate
# (POST .../deactivate/) instead of hard-delete; there is no DELETE endpoint.

class WarehouseListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    filterset_class  = WarehouseFilter
    search_fields    = ['code', 'name']
    ordering_fields  = ['name', 'code', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class WarehouseDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a warehouse. No DELETE — deactivate instead."""

    queryset          = Warehouse.objects.all()
    serializer_class  = WarehouseSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class WarehouseDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = Warehouse.objects.all()
    serializer_class   = WarehouseSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        warehouse = self.get_object()
        if warehouse.is_active:
            warehouse.is_active = False
            warehouse.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(warehouse).data)


class BranchWarehouseListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = BranchWarehouse.objects.select_related('branch', 'warehouse').all()
    serializer_class = BranchWarehouseSerializer
    filterset_class  = BranchWarehouseFilter
    ordering_fields  = ['branch', 'role', 'created_at']
    ordering         = ['branch_id', 'role']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class BranchWarehouseDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    queryset          = BranchWarehouse.objects.select_related('branch', 'warehouse').all()
    serializer_class  = BranchWarehouseSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class BranchWarehouseDeactivateView(TenantMixin, generics.GenericAPIView):
    queryset           = BranchWarehouse.objects.select_related('branch', 'warehouse').all()
    serializer_class   = BranchWarehouseSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        link = self.get_object()
        if link.is_active:
            link.is_active = False
            link.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(link).data)


class BranchNestedWarehouseListCreateView(TenantMixin, generics.ListCreateAPIView):
    """`/api/branches/{branch_pk}/warehouses/` — links scoped to one branch.

    Convenience surface from MASTER_DATA_CONTRACT.md §4.4. The branch comes
    from the URL (validated against the tenant) and is injected before
    serializer validation so the body never needs to repeat it.
    """

    queryset         = BranchWarehouse.objects.select_related('branch', 'warehouse').all()
    serializer_class = BranchWarehouseSerializer
    filterset_class  = BranchWarehouseFilter
    ordering         = ['role']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def _branch(self):
        return get_object_or_404(Branch, pk=self.kwargs['branch_pk'], tenant=self._tenant())

    def get_queryset(self):
        return super().get_queryset().filter(branch=self._branch())

    def create(self, request, *args, **kwargs):
        branch = self._branch()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['branch'] = branch.pk
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=self._tenant())
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


# ── Per-Warehouse Stock Balances (Phase 1.5 Slice J — read-only) ──────────────
# Cached balances maintained from stock movements only; there is intentionally
# no POST/PATCH/DELETE — changing stock goes through a movement, never a direct
# balance write (mirrors how Product.stock has no direct "set" endpoint).

class WarehouseStockListView(TenantMixin, generics.ListAPIView):
    """GET /api/inventory/warehouse-stock/ — cached per-warehouse balances.

    Filter by ?warehouse= / ?product= / ?low_stock= / ?has_stock=.
    """

    queryset           = WarehouseStock.objects.select_related('product', 'warehouse').all()
    serializer_class   = WarehouseStockSerializer
    permission_classes = [IsManagerOrAbove]
    filterset_class    = WarehouseStockFilter
    ordering_fields    = ['quantity', 'updated_at']
    ordering           = ['product_id', 'warehouse_id']


class ProductWarehouseStockView(TenantMixin, generics.ListAPIView):
    """GET /api/products/{pk}/warehouse-stocks/ — one product across all warehouses."""

    serializer_class   = WarehouseStockSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return (
            WarehouseStock.objects
            .select_related('product', 'warehouse')
            .filter(tenant=self._tenant(), product_id=self.kwargs['pk'])
            .order_by('warehouse_id')
        )


class ProductCostMovementListView(TenantMixin, generics.ListAPIView):
    """GET /api/products/{pk}/cost-movements/ — InventoryCostMovement audit
    trail for one product, newest-first (Sprint 3 Batch 4).

    Read-only; every row is written exclusively by `pos.services.costing`.
    A product id that doesn't exist or belongs to another tenant yields an
    empty list, not a 404 — same precedent as `ProductWarehouseStockView`
    above, which this view mirrors.
    """

    serializer_class   = InventoryCostMovementSerializer
    permission_classes = [IsManagerOrAbove]
    filterset_class    = InventoryCostMovementFilter

    def get_queryset(self):
        return (
            InventoryCostMovement.objects
            .select_related('actor_user')
            .filter(tenant=self._tenant(), product_id=self.kwargs['pk'])
            # Meta.ordering = ['-occurred_at', '-id'] on the model already
            # gives newest-first.
        )


COST_HISTORY_EXPORT_COLUMNS = [
    'Date', 'Source', 'Qty received', 'Unit cost received',
    'Avg cost before', 'Avg cost after', 'Note',
]


def _cost_history_export_rows(pk, tenant, request):
    """Shared queryset + row-building for all three export formats — same
    filter (`InventoryCostMovementFilter`) and column set the drawer's own
    table uses, so what a user sees on screen is exactly what they export.
    Cross-tenant/nonexistent product ids yield zero rows (still a valid,
    openable empty file), matching `ProductCostMovementListView`'s own
    "empty list, not 404" precedent (Sprint 3 Batch 4)."""
    qs = InventoryCostMovement.objects.filter(tenant=tenant, product_id=pk)
    qs = InventoryCostMovementFilter(request.query_params, queryset=qs).qs
    qs = qs.order_by('-occurred_at', '-id')
    for m in qs.iterator(chunk_size=500):
        yield [
            m.occurred_at.strftime('%Y-%m-%d %H:%M'),
            f'{m.source_document_type}{f" #{m.source_document_id}" if m.source_document_id else ""}' if m.source_document_type else '',
            m.quantity_received if m.quantity_received is not None else '',
            m.unit_cost_received if m.unit_cost_received is not None else '',
            m.avg_cost_before,
            m.avg_cost_after,
            m.note,
        ]


@api_view(['GET'])
@permission_classes([IsManagerOrAbove])
def product_cost_movements_export(request, pk):
    """
    GET /api/products/{pk}/cost-movements/export/?export_format=csv|xlsx|pdf&start_date=&end_date=&source_document_type=

    Sprint 4 Batch 4. Same date-range/source-type filtering as the list
    endpoint (`InventoryCostMovementFilter`), exported as a plain tabular
    report in the caller's chosen format — no charts embedded, matching
    what "export cost history" literally asked for.

    NOTE: the query param is `export_format`, not `format` — DRF reserves
    `?format=` (`URL_FORMAT_OVERRIDE`) for its own content-negotiation and
    raises Http404 when the value doesn't match a registered renderer
    (confirmed the hard way while building this). Using a differently-named
    param sidesteps that entirely rather than fighting DRF's renderer
    machinery for a single endpoint.
    """
    tenant = getattr(request.user, 'tenant', None)
    fmt = (request.query_params.get('export_format') or 'csv').lower()
    if fmt not in ('csv', 'xlsx', 'pdf'):
        return Response({'detail': "Invalid export_format: expected 'csv', 'xlsx', or 'pdf'."}, status=status.HTTP_400_BAD_REQUEST)

    product_name = (
        Product.objects.filter(pk=pk, tenant=tenant).values_list('name', flat=True).first()
        if tenant else Product.objects.filter(pk=pk).values_list('name', flat=True).first()
    )
    slug = (product_name or f'product-{pk}').lower().replace(' ', '-')
    date_tag = ''
    start_date, end_date = request.query_params.get('start_date'), request.query_params.get('end_date')
    if start_date and end_date:
        date_tag = f'-{start_date}_{end_date}'
    basename = f'cost-history-{slug}{date_tag}'

    rows = list(_cost_history_export_rows(pk, tenant, request))

    if fmt == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{basename}.csv"'
        response.write('﻿')  # BOM so Excel opens Arabic/UTF-8 columns correctly
        writer = csv.writer(response)
        writer.writerow(COST_HISTORY_EXPORT_COLUMNS)
        for row in rows:
            writer.writerow(row)
        return response

    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = 'Cost History'
        ws.append(COST_HISTORY_EXPORT_COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([str(v) if v != '' else '' for v in row])
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{basename}.xlsx"'
        wb.save(response)
        return response

    # fmt == 'pdf'
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter))
    table_data = [COST_HISTORY_EXPORT_COLUMNS] + [[str(v) for v in row] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    doc.build([table])
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{basename}.pdf"'
    return response


class WarehouseInventoryView(TenantMixin, generics.ListAPIView):
    """GET /api/inventory/warehouses/{pk}/stock/ — all product balances in a warehouse."""

    serializer_class   = WarehouseStockSerializer
    permission_classes = [IsManagerOrAbove]
    filterset_class    = WarehouseStockFilter

    def get_queryset(self):
        return (
            WarehouseStock.objects
            .select_related('product', 'warehouse')
            .filter(tenant=self._tenant(), warehouse_id=self.kwargs['pk'])
            .order_by('product_id')
        )


# ── Category Trees (Sprint 2 Batch 2 — MASTER_DATA_CONTRACT §3) ──────────────
# Two independent hierarchical trees. Same conventions as the unit/warehouse
# routes: tenant-scoped, Manager+ writes, Cashier+ reads, deactivate instead
# of delete (children PROTECT their parent, and history must stay valid).
# The legacy flat `categories/` route stays frozen as-is.


class SalesCategoryListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = SalesCategory.objects.select_related('parent').all()
    serializer_class = SalesCategorySerializer
    filterset_class  = SalesCategoryFilter
    search_fields    = ['name']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class SalesCategoryDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a sales category. No DELETE — deactivate instead."""

    queryset          = SalesCategory.objects.select_related('parent').all()
    serializer_class  = SalesCategorySerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class SalesCategoryDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = SalesCategory.objects.all()
    serializer_class   = SalesCategorySerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        category = self.get_object()
        if category.is_active:
            category.is_active = False
            category.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(category).data)


class InventoryCategoryListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = InventoryCategory.objects.select_related('parent').all()
    serializer_class = InventoryCategorySerializer
    filterset_class  = InventoryCategoryFilter
    search_fields    = ['name']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class InventoryCategoryDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH an inventory category. No DELETE — deactivate instead."""

    queryset          = InventoryCategory.objects.select_related('parent').all()
    serializer_class  = InventoryCategorySerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class InventoryCategoryDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = InventoryCategory.objects.all()
    serializer_class   = InventoryCategorySerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        category = self.get_object()
        if category.is_active:
            category.is_active = False
            category.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(category).data)


# ── Dynamic Units (Sprint 2 Batch 1 — MASTER_DATA_CONTRACT §2.4) ─────────────
# Same conventions as the warehouse routes: tenant-scoped, Manager+ writes,
# Cashier+ reads, deactivate instead of delete.


class UnitGroupListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = UnitGroup.objects.all()
    serializer_class = UnitGroupSerializer
    filterset_class  = UnitGroupFilter
    search_fields    = ['name']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class UnitGroupDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a unit group. No DELETE — deactivate instead."""

    queryset          = UnitGroup.objects.all()
    serializer_class  = UnitGroupSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class UnitGroupDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = UnitGroup.objects.all()
    serializer_class   = UnitGroupSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        group = self.get_object()
        if group.is_active:
            group.is_active = False
            group.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(group).data)


class UnitListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = Unit.objects.select_related('unit_group').all()
    serializer_class = UnitSerializer
    filterset_class  = UnitFilter
    search_fields    = ['name', 'symbol']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['unit_group_id', 'name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class UnitDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a unit. No DELETE — deactivate instead."""

    queryset          = Unit.objects.select_related('unit_group').all()
    serializer_class  = UnitSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class UnitDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = Unit.objects.all()
    serializer_class   = UnitSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        unit = self.get_object()
        if unit.is_active:
            unit.is_active = False
            unit.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(unit).data)


class StandardUnitCodeListView(APIView):
    """GET — the static UN/CEFACT Rec 20 subset (Sprint 2 Phase 1.5).

    Pure enum readout, no DB query, no tenant scoping — the list is shared
    across every tenant, same as `Product.unit`'s legacy choices. Powers a
    future `Unit.standard_code` picker (Batch 5b); usable for manual
    verification today.
    """

    permission_classes = [IsCashierOrAbove]

    def get(self, request):
        return Response([
            {'code': code, 'label': label}
            for code, label in StandardUnitCode.choices
        ])


class ProductTypeMetadataListView(APIView):
    """GET — the full product-type behavior + required-field matrix (Batch 8
    architectural-improvement pass), read straight off
    `pos.services.product_types.PRODUCT_TYPE_BEHAVIOR`.

    This is the single source of truth the frontend's Dynamic Product Form
    renders from — no `product_type` rule is duplicated in React. Every
    rule this data drives (can_sell, show_on_pos, required fields) is still
    independently enforced server-side regardless of what the form does
    with this payload; it only controls what's *shown*, never what's
    *allowed*.

    Pure enum readout, no DB query, no tenant scoping — same shape as
    `StandardUnitCodeListView` right above it.
    """

    permission_classes = [IsCashierOrAbove]

    def get(self, request):
        return Response(product_type_metadata())


class _ProductScopedMixin(TenantMixin):
    """Resolves the parent product from `product_pk`, tenant-scoped.

    404s for a product outside the caller's tenant (same isolation contract
    as every other product route) and passes the product into the serializer
    context so belongs-to-product rules can run.
    """

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


class ProductUnitListCreateView(_ProductScopedMixin, generics.ListCreateAPIView):
    queryset         = ProductUnit.objects.select_related('unit', 'unit__unit_group').all()
    serializer_class = ProductUnitSerializer
    ordering         = ['-is_base', 'id']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductUnitDetailView(_ProductScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one product-unit mapping. No DELETE — deactivate via PATCH."""

    queryset          = ProductUnit.objects.select_related('unit').all()
    serializer_class  = ProductUnitSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductBarcodeUnitListCreateView(_ProductScopedMixin, generics.ListCreateAPIView):
    """GET/POST per-pack barcodes for one product (contract §2.4).

    Scan-precedence wiring (resolve these before `Product.barcode`) is
    Sprint 2 Batch 3 — this endpoint only manages the mappings.
    """

    queryset         = ProductBarcodeUnit.objects.select_related(
        'product_unit', 'product_unit__unit').all()
    serializer_class = ProductBarcodeUnitSerializer
    ordering         = ['id']

    def get_queryset(self):
        return super().get_queryset().filter(product_id=self.kwargs['product_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


# ── Unit-aware pricing (Sprint 2 Batch 4 remainder — MASTER_DATA_CONTRACT §2) ─
# PriceTier is tenant-scoped and flat (same conventions as UnitGroup).
# ProductUnitTierPrice is nested two levels deep: product -> product_unit ->
# tier-prices, mirroring the ProductUnit / ProductBarcodeUnit nesting pattern.


class PriceTierListCreateView(TenantMixin, generics.ListCreateAPIView):
    queryset         = PriceTier.objects.all()
    serializer_class = PriceTierSerializer
    search_fields    = ['name']
    ordering_fields  = ['name', 'created_at']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class PriceTierDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH a price tier. No DELETE — deactivate instead."""

    queryset          = PriceTier.objects.all()
    serializer_class  = PriceTierSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class PriceTierDeactivateView(TenantMixin, generics.GenericAPIView):
    """POST — soft-delete by flipping `is_active=False`."""

    queryset           = PriceTier.objects.all()
    serializer_class   = PriceTierSerializer
    permission_classes = [IsManagerOrAbove]

    def post(self, request, *args, **kwargs):
        tier = self.get_object()
        if tier.is_active:
            tier.is_active = False
            tier.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(tier).data)


class _ProductUnitScopedMixin(TenantMixin):
    """Resolves the parent product AND product_unit from the URL, tenant-scoped.

    404s for either falling outside the caller's tenant or the product_unit
    not belonging to the product (same isolation contract as
    `_ProductScopedMixin`).
    """

    def get_product(self):
        qs = Product.objects.all()
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['product_pk'])

    def get_product_unit(self):
        qs = ProductUnit.objects.filter(product_id=self.kwargs['product_pk'])
        tenant = self._tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return get_object_or_404(qs, pk=self.kwargs['unit_pk'])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['product'] = self.get_product()
        ctx['product_unit'] = self.get_product_unit()
        return ctx

    def perform_create(self, serializer):
        tenant = self._tenant()
        product_unit = self.get_product_unit()
        if tenant:
            serializer.save(tenant=tenant, product=product_unit.product, product_unit=product_unit)
        else:
            serializer.save(product=product_unit.product, product_unit=product_unit)


class ProductUnitTierPriceListCreateView(_ProductUnitScopedMixin, generics.ListCreateAPIView):
    queryset         = ProductUnitTierPrice.objects.select_related('price_tier').all()
    serializer_class = ProductUnitTierPriceSerializer
    ordering         = ['price_tier_id']

    def get_queryset(self):
        return super().get_queryset().filter(product_unit_id=self.kwargs['unit_pk'])

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


class ProductUnitTierPriceDetailView(_ProductUnitScopedMixin, generics.RetrieveUpdateAPIView):
    """GET / PATCH one tier price. No DELETE — deactivate via PATCH."""

    queryset          = ProductUnitTierPrice.objects.select_related('price_tier').all()
    serializer_class  = ProductUnitTierPriceSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().filter(product_unit_id=self.kwargs['unit_pk'])

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]


# ── Purchase Invoices (Phase 1.5 Slice H — posting) ───────────────────────────

class PurchaseInvoiceListCreateView(TenantMixin, generics.ListCreateAPIView):
    """GET list + POST create-and-post a stock-item purchase invoice.

    POST runs the full atomic posting (stock + moving-avg cost + finance/AP)
    via the serializer → `pos.services.purchase_invoices`. Requires an
    `Idempotency-Key` header (Hotfix Pack — was previously optional, which
    let a bare retry double-post stock/cost/AP/cash) so a retried POST
    replays the original response instead of double-posting.
    """

    queryset = (
        PurchaseInvoice.objects
        .select_related('supplier', 'branch', 'source_account', 'payment_method')
        .prefetch_related('lines', 'lines__product')
        .all()
    )
    serializer_class = PurchaseInvoiceSerializer
    ordering         = ['-created_at']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def perform_create(self, serializer):
        # tenant + actor are resolved from the request context inside the
        # serializer/service, so no tenant kwarg is injected here.
        serializer.save()

    def create(self, request, *args, **kwargs):
        tenant = self._tenant()
        key = (request.headers.get('Idempotency-Key') or '').strip()

        if not key:
            return Response(
                {'error': {
                    'code': 'IDEMPOTENCY_KEY_REQUIRED',
                    'detail': 'Posting a purchase invoice requires an Idempotency-Key header.',
                }},
                status=status.HTTP_400_BAD_REQUEST,
            )

        look = idempotency.lookup(
            tenant=tenant, key=key, payload=request.data,
            method=request.method, path=request.path, user=request.user,
        )
        if look.replay:
            return Response(look.body, status=look.status)
        if look.conflict:
            return Response(
                {'error': {
                    'code': 'IDEMPOTENCY_CONFLICT',
                    'detail': 'Idempotency-Key reused with a different payload.',
                }},
                status=status.HTTP_409_CONFLICT,
            )

        # Business-uniqueness safety net: if the client supplied the
        # supplier's own invoice number, a repeat of (tenant, supplier,
        # reference) is almost certainly the same real-world document —
        # catches the case an Idempotency-Key retry can't, where a buggy
        # client mints a *fresh* key on every retry. Only fires when a
        # reference is actually provided; the overwhelming majority of
        # invoices that omit it are completely unaffected.
        reference   = (request.data.get('reference') or '').strip()
        supplier_id = request.data.get('supplier')
        if reference and supplier_id and tenant is not None:
            if PurchaseInvoice.objects.filter(
                    tenant=tenant, supplier_id=supplier_id, reference=reference).exists():
                return Response(
                    {'error': {
                        'code': 'SUPPLIER_REFERENCE_DUPLICATE',
                        'detail': (
                            f'A purchase invoice with reference {reference!r} already '
                            f'exists for this supplier.'
                        ),
                    }},
                    status=status.HTTP_409_CONFLICT,
                )

        response = super().create(request, *args, **kwargs)

        idempotency.save(
            tenant=tenant, key=key, payload=request.data,
            method=request.method, path=request.path,
            response_status=response.status_code, response_body=response.data,
            user=request.user,
        )
        return response


class PurchaseInvoiceDetailView(TenantMixin, generics.RetrieveAPIView):
    """GET one purchase invoice. No update/delete in this slice."""

    queryset = (
        PurchaseInvoice.objects
        .select_related('supplier', 'branch', 'source_account', 'payment_method')
        .prefetch_related('lines', 'lines__product')
        .all()
    )
    serializer_class   = PurchaseInvoiceSerializer
    permission_classes = [IsCashierOrAbove]
