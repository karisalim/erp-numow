"""End-to-end tests for the Hyper Fekra Quesna workflows.

Covers:
    * Weight-encoded barcode scanning (Task 1)
    * Sale checkout with amount_paid / change (Task 2)
    * Dynamic receipt layout (Task 3)
"""

from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from unittest.mock import patch

from accounts.models import (
    Branch, FinancialAccount, PaymentMethod, Supplier, Tenant, Terminal, User,
)
from accounts.services import account_movements as account_service
from accounts.services import supplier_ap as supplier_ap_service
from pos.models import (
    BranchWarehouse, Category, Payment, Product, PurchaseInvoice,
    PurchaseInvoiceLine, Sale, StockMovement, Warehouse,
)
from pos.services import purchase_invoices as purchase_invoice_service
from pos.services import stock_movements as stock_movement_service
from pos.views import _parse_weight_encoded_barcode


class WeightEncodedBarcodeTests(APITestCase):
    """Task 1: Parse `23 + PLU(5) + weight(5) + checksum(1)` barcodes."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Hyper Fekra Quesna', scale_barcode_prefix='23')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Main')
        cls.terminal = Terminal.objects.create(branch=cls.branch, name='POS-1', serial='SER-001')
        cls.cashier = User.objects.create_user(
            username='dunya', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Fruits')
        # Weighted product: 140 EGP/kg, PLU = '09524'
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Bananas', barcode='BAN-001', sku='SKU-BAN',
            price=Decimal('140.00'), cost=Decimal('80.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('500'),
            weighted=True, unit=Product.Unit.KG, plu='09524',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def test_parser_helper_decodes_structure(self):
        plu, weight = _parse_weight_encoded_barcode('2309524001448', '23')
        self.assertEqual(plu, '09524')
        self.assertEqual(weight, Decimal('0.144'))

    def test_parser_rejects_wrong_prefix(self):
        self.assertIsNone(_parse_weight_encoded_barcode('2109524001448', '23'))

    def test_parser_rejects_wrong_length(self):
        self.assertIsNone(_parse_weight_encoded_barcode('2309524', '23'))
        self.assertIsNone(_parse_weight_encoded_barcode('23095240014488', '23'))

    def test_scan_endpoint_returns_product_qty_and_line_total(self):
        """The headline acceptance test from the spec.

        Barcode '2309524001448' → PLU 09524, qty 0.144, line total 20.16.
        """
        url = reverse('product-scan', kwargs={'barcode': '2309524001448'})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        body = resp.json()
        self.assertEqual(body['type'], 'weight_encoded')
        self.assertEqual(body['product']['id'], self.product.id)
        self.assertEqual(body['plu'], '09524')
        self.assertEqual(Decimal(body['quantity']),   Decimal('0.144'))
        self.assertEqual(Decimal(body['price_each']), Decimal('140.00'))
        self.assertEqual(Decimal(body['line_total']), Decimal('20.16'))

    def test_scan_endpoint_falls_back_to_plain_barcode(self):
        """Non weight-encoded barcodes fall through to the regular lookup."""
        url = reverse('product-scan', kwargs={'barcode': 'BAN-001'})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body['type'], 'barcode')
        self.assertEqual(body['product']['id'], self.product.id)

    def test_scan_endpoint_404_when_plu_missing(self):
        # PLU 00000 doesn't map to any product in this tenant.
        url = reverse('product-scan', kwargs={'barcode': '2300000001448'})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class SaleCheckoutPaymentTests(APITestCase):
    """Task 2: POST /api/sales/ persists Payment with amount_paid + change."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='Hyper Fekra Quesna', receipt_header='ولا اعلى من الجودة')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Quesna')
        cls.terminal = Terminal.objects.create(branch=cls.branch, name='خزينة رقم 2', serial='KZ-2')
        cls.cashier = User.objects.create_user(
            username='dunya', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Fruits')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Bananas', barcode='BAN-001', sku='SKU-BAN',
            price=Decimal('140.00'), cost=Decimal('80.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('500'),
            weighted=True, unit=Product.Unit.KG, plu='09524',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _post_sale(self, paid_field_name='amount_paid'):
        """Same cart, parameterised on whether we send `paid` or `amount_paid`."""
        body = {
            'items': [{
                'product':    self.product.id,
                'qty':        '0.144',
                'price_each': '140.00',
            }],
            'method':         'cash',
            paid_field_name:  '50.00',
        }
        url = reverse('sale-list')
        return self.client.post(url, body, format='json')

    def test_amount_paid_alias_creates_sale_and_payment_with_correct_change(self):
        """The headline acceptance test from the spec.

        total = 20.16, amount_paid = 50.00 → change = 29.84, item_count = 1.
        """
        resp = self._post_sale(paid_field_name='amount_paid')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        sale_uuid = resp.json()['sale_uuid']

        sale = Sale.objects.get(sale_uuid=sale_uuid)
        self.assertEqual(sale.total,  Decimal('20.16'))
        self.assertEqual(sale.paid,   Decimal('50.00'))
        self.assertEqual(sale.change, Decimal('29.84'))
        self.assertEqual(sale.items.count(), 1)
        self.assertEqual(sale.payment_method_hint, 'cash')

        payment = Payment.objects.get(sale=sale)
        self.assertEqual(payment.amount,      Decimal('20.16'))
        self.assertEqual(payment.amount_paid, Decimal('50.00'))
        self.assertEqual(payment.change,      Decimal('29.84'))
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.method, 'cash')

    def test_legacy_paid_field_still_works(self):
        """Backward compatibility — older clients sending `paid` keep working."""
        resp = self._post_sale(paid_field_name='paid')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        sale = Sale.objects.get(sale_uuid=resp.json()['sale_uuid'])
        payment = Payment.objects.get(sale=sale)
        self.assertEqual(payment.amount_paid, Decimal('50.00'))
        self.assertEqual(payment.change,      Decimal('29.84'))

    def test_oversell_succeeds_with_warning_and_negative_stock(self):
        """Selling more than on-hand stock is allowed per FLOW.md.

        Regression guard: a `stock >= 0` CHECK constraint used to make this
        explode with HTTP 500 (CheckViolation on the fallback update). The
        constraint was removed; oversell now lands the row at negative
        stock and surfaces a warning to the cashier.
        """
        # Zero out stock so the next sale is guaranteed to oversell.
        self.product.stock = Decimal('0')
        self.product.save(update_fields=['stock'])

        body = {
            'items': [{
                'product':    self.product.id,
                'qty':        '1',
                'price_each': '140.00',
            }],
            'method':      'cash',
            'amount_paid': '200.00',
        }
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        data = resp.json()
        self.assertTrue(data['warnings'], 'Expected oversell warning in response.')
        self.assertIn('Only 0', data['warnings'][0])

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('-1.000'))


class ReceiptLayoutTests(APITestCase):
    """Task 3: GET /api/sales/<uuid>/receipt/ pulls dynamic config from Tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            name='Hyper Fekra Quesna',
            receipt_header='مرحبا بكم في هايبر فكرة قويسنا',
            receipt_footer='شكرا لزيارتكم - الاستبدال خلال 7 أيام',
            vat_number='123-456-789',
            phone='01000000000',
            address='قويسنا، المنوفية',
            currency='EGP',
        )
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='Quesna')
        cls.terminal = Terminal.objects.create(branch=cls.branch, name='خزينة رقم 2', serial='KZ-2')
        cls.cashier = User.objects.create_user(
            username='dunya', password='pw', first_name='دنيا',
            role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch, terminal=cls.terminal,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Fruits')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Bananas', barcode='BAN-001', sku='SKU-BAN',
            price=Decimal('140.00'), cost=Decimal('80.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('500'),
            weighted=True, unit=Product.Unit.KG, plu='09524',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _create_sale(self):
        url = reverse('sale-list')
        body = {
            'items': [{
                'product':    self.product.id,
                'qty':        '0.144',
                'price_each': '140.00',
            }],
            'method':      'cash',
            'amount_paid': '50.00',
        }
        resp = self.client.post(url, body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        return resp.json()['sale_uuid']

    def test_receipt_pulls_dynamic_header_footer_from_tenant(self):
        sale_uuid = self._create_sale()
        url = reverse('sale-receipt', kwargs={'sale_uuid': sale_uuid})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        body = resp.json()
        self.assertIn('auto',   body)
        self.assertIn('config', body)
        self.assertIn('lines',  body)
        self.assertIn('totals', body)

        # Dynamic config — straight from Tenant row, no hardcoded policy.
        self.assertEqual(body['config']['receipt_header'], 'مرحبا بكم في هايبر فكرة قويسنا')
        self.assertEqual(body['config']['receipt_footer'], 'شكرا لزيارتكم - الاستبدال خلال 7 أيام')
        self.assertEqual(body['config']['vat_number'],     '123-456-789')
        self.assertEqual(body['config']['currency'],       'EGP')

        # Auto-filled fields — terminal/cashier/serial come from DB, not body.
        self.assertEqual(body['auto']['terminal'], 'خزينة رقم 2')
        self.assertEqual(body['auto']['cashier'], 'دنيا')
        self.assertEqual(body['auto']['columns'], ['الصنف', 'الكمية', 'السعر', 'القيمة'])

        # Totals
        self.assertEqual(body['totals']['total_due'],   '20.16')
        self.assertEqual(body['totals']['amount_paid'], '50.00')
        self.assertEqual(body['totals']['change'],      '29.84')
        self.assertEqual(body['totals']['item_count'],  1)

    def test_receipt_picks_up_dashboard_edits_live(self):
        """Admin edits tenant header → next receipt shows the new text. No
        code change, no redeploy."""
        sale_uuid = self._create_sale()
        self.tenant.receipt_header = 'NEW POLICY TEXT'
        self.tenant.save(update_fields=['receipt_header'])

        url = reverse('sale-receipt', kwargs={'sale_uuid': sale_uuid})
        resp = self.client.get(url)
        self.assertEqual(resp.json()['config']['receipt_header'], 'NEW POLICY TEXT')


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 1.5 — Dynamic Warehouses / Branch Warehouses (backend foundation)
# ══════════════════════════════════════════════════════════════════════════════

class _WarehouseTestBase(APITestCase):
    """Two-tenant fixture for warehouse isolation + linking tests."""

    @classmethod
    def setUpTestData(cls):
        # Tenant A
        cls.tenant = Tenant.objects.create(name='Tenant A')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='A-Main')
        cls.manager = User.objects.create_user(
            username='mgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.cashier = User.objects.create_user(
            username='csh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Drinks')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Cola', barcode='COLA-1', sku='SKU-COLA',
            price=Decimal('10.00'), cost=Decimal('6.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )

        # Tenant B (foreign — for isolation / cross-tenant tests)
        cls.tenant_b = Tenant.objects.create(name='Tenant B')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='B-Main')
        cls.manager_b = User.objects.create_user(
            username='mgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant_b, branch=cls.branch_b,
        )
        cls.warehouse_b = Warehouse.objects.create(
            tenant=cls.tenant_b, code='WB-1', name='B Store',
        )

    def _wh(self, tenant, code='WA-1', name='A Store', **kw):
        return Warehouse.objects.create(tenant=tenant, code=code, name=name, **kw)


class WarehouseApiTests(_WarehouseTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_create_list_retrieve_update_deactivate(self):
        # Create
        resp = self.client.post(reverse('warehouse-list'), {
            'code': 'MAIN', 'name': 'Main Store', 'warehouse_type': 'main',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        wh_id = resp.json()['id']
        # The view injects tenant — never trusted from the body.
        self.assertEqual(Warehouse.objects.get(pk=wh_id).tenant_id, self.tenant.id)

        # List
        resp = self.client.get(reverse('warehouse-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [w['id'] for w in resp.json()['results']]
        self.assertIn(wh_id, ids)

        # Retrieve
        resp = self.client.get(reverse('warehouse-detail', kwargs={'pk': wh_id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['warehouse_type'], 'main')

        # Update
        resp = self.client.patch(reverse('warehouse-detail', kwargs={'pk': wh_id}),
                                 {'name': 'Renamed Store'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['name'], 'Renamed Store')

        # Deactivate (soft delete)
        resp = self.client.post(reverse('warehouse-deactivate', kwargs={'pk': wh_id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertFalse(Warehouse.objects.get(pk=wh_id).is_active)

    def test_tenant_isolation(self):
        # Tenant B's warehouse must be invisible to Tenant A.
        resp = self.client.get(reverse('warehouse-list'))
        ids = [w['id'] for w in resp.json()['results']]
        self.assertNotIn(self.warehouse_b.id, ids)

        resp = self.client.get(reverse('warehouse-detail', kwargs={'pk': self.warehouse_b.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_code_unique_per_tenant_but_shared_across_tenants(self):
        self.client.post(reverse('warehouse-list'),
                         {'code': 'DUP', 'name': 'First'}, format='json')
        # Same code, same tenant → rejected.
        resp = self.client.post(reverse('warehouse-list'),
                                {'code': 'DUP', 'name': 'Second'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Same code in a different tenant → allowed.
        self.client.force_authenticate(user=self.manager_b)
        resp = self.client.post(reverse('warehouse-list'),
                                {'code': 'DUP', 'name': 'B Dup'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_cashier_cannot_write_but_can_read(self):
        self.client.force_authenticate(user=self.cashier)
        # Read OK
        self.assertEqual(self.client.get(reverse('warehouse-list')).status_code,
                         status.HTTP_200_OK)
        # Create forbidden
        resp = self.client.post(reverse('warehouse-list'),
                                {'code': 'X', 'name': 'X'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        # Deactivate forbidden
        wh = self._wh(self.tenant)
        resp = self.client.post(reverse('warehouse-deactivate', kwargs={'pk': wh.id}))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_warehouse_type_is_rejected(self):
        resp = self.client.post(reverse('warehouse-list'), {
            'code': 'BAD', 'name': 'Bad Type', 'warehouse_type': 'invalid',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_is_idempotent(self):
        wh = self._wh(self.tenant, code='WA-2', name='A Store 2')
        first = self.client.post(reverse('warehouse-deactivate', kwargs={'pk': wh.id}))
        second = self.client.post(reverse('warehouse-deactivate', kwargs={'pk': wh.id}))
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        wh.refresh_from_db()
        self.assertFalse(wh.is_active)


class BranchWarehouseApiTests(_WarehouseTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)
        self.warehouse = self._wh(self.tenant)

    def _link_body(self, **over):
        body = {'branch': self.branch.id, 'warehouse': self.warehouse.id,
                'role': 'sales', 'is_default': False}
        body.update(over)
        return body

    def test_create_link(self):
        resp = self.client.post(reverse('branch-warehouse-list'),
                                self._link_body(is_default=True), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        link = BranchWarehouse.objects.get(pk=resp.json()['id'])
        self.assertEqual(link.tenant_id, self.tenant.id)
        self.assertEqual(link.role, 'sales')

    def test_cross_tenant_link_rejected(self):
        # Branch of tenant A + warehouse of tenant B → 400.
        resp = self.client.post(reverse('branch-warehouse-list'),
                                self._link_body(warehouse=self.warehouse_b.id),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_active_link_rejected(self):
        self.client.post(reverse('branch-warehouse-list'), self._link_body(), format='json')
        resp = self.client.post(reverse('branch-warehouse-list'), self._link_body(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_is_idempotent_and_preserves_history(self):
        resp = self.client.post(reverse('branch-warehouse-list'), self._link_body(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        link_id = resp.json()['id']

        first = self.client.post(reverse('branch-warehouse-deactivate', kwargs={'pk': link_id}))
        second = self.client.post(reverse('branch-warehouse-deactivate', kwargs={'pk': link_id}))
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        link = BranchWarehouse.objects.get(pk=link_id)
        self.assertFalse(link.is_active)
        self.assertEqual(link.branch_id, self.branch.id)
        self.assertEqual(link.warehouse_id, self.warehouse.id)

    def test_one_default_per_branch_per_role(self):
        wh2 = self._wh(self.tenant, code='WA-2', name='A Store 2')
        # First default for (branch, sales) → OK.
        resp = self.client.post(reverse('branch-warehouse-list'),
                                self._link_body(is_default=True), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        # Second default for the same (branch, sales) via another warehouse → 400.
        resp = self.client.post(reverse('branch-warehouse-list'),
                                self._link_body(warehouse=wh2.id, is_default=True),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # A different role on the same branch can still be its own default.
        resp = self.client.post(reverse('branch-warehouse-list'),
                                self._link_body(warehouse=wh2.id, role='returns',
                                                is_default=True),
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_nested_branch_endpoint_injects_branch(self):
        url = reverse('branch-warehouse-nested-list', kwargs={'branch_pk': self.branch.id})
        # Body omits `branch` — the URL supplies it.
        resp = self.client.post(url, {'warehouse': self.warehouse.id, 'role': 'kitchen'},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(BranchWarehouse.objects.get(pk=resp.json()['id']).branch_id,
                         self.branch.id)

        # Listing the nested endpoint is scoped to that branch only.
        resp = self.client.get(url)
        self.assertTrue(all(row['branch'] == self.branch.id for row in resp.json()['results']))


class StockMovementWarehouseTests(_WarehouseTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)
        self.warehouse = self._wh(self.tenant)

    def test_create_with_warehouse_persists_and_is_filterable(self):
        resp = self.client.post(reverse('stock-movement-list'), {
            'product': self.product.id, 'qty': '5.000',
            'movement_type': 'receive_in', 'warehouse': self.warehouse.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.json()['warehouse'], self.warehouse.id)

        mv = StockMovement.objects.get(pk=resp.json()['id'])
        self.assertEqual(mv.warehouse_id, self.warehouse.id)

        # Filterable by ?warehouse=
        resp = self.client.get(reverse('stock-movement-list'), {'warehouse': self.warehouse.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r['warehouse'] == self.warehouse.id for r in resp.json()['results']))
        self.assertGreaterEqual(len(resp.json()['results']), 1)

    def test_create_without_warehouse_still_works(self):
        """Backward compatibility — warehouse is optional; ledger still chains."""
        resp = self.client.post(reverse('stock-movement-list'), {
            'product': self.product.id, 'qty': '3.000', 'movement_type': 'receive_in',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        mv = StockMovement.objects.get(pk=resp.json()['id'])
        self.assertIsNone(mv.warehouse_id)
        # Running-quantity columns are still populated by the service.
        self.assertIsNotNone(mv.quantity_after)

    def test_service_records_warehouse_for_in_and_out_movements(self):
        inbound = stock_movement_service.record_stock_in(
            product=self.product,
            quantity='2.000',
            movement_type=StockMovement.MovementType.RECEIVE_IN,
            warehouse=self.warehouse,
        )
        self.assertEqual(inbound.warehouse_id, self.warehouse.id)

        outbound = stock_movement_service.record_stock_out(
            product=self.product,
            quantity='1.000',
            movement_type=StockMovement.MovementType.SALE_OUT,
            warehouse=self.warehouse,
        )
        self.assertEqual(outbound.warehouse_id, self.warehouse.id)

    def test_service_rejects_cross_tenant_warehouse(self):
        with self.assertRaises(stock_movement_service.StockMovementError):
            stock_movement_service.record_stock_in(
                product=self.product,
                quantity='1.000',
                movement_type=StockMovement.MovementType.RECEIVE_IN,
                warehouse=self.warehouse_b,
            )

    def test_cross_tenant_warehouse_rejected_on_movement(self):
        resp = self.client.post(reverse('stock-movement-list'), {
            'product': self.product.id, 'qty': '1.000',
            'movement_type': 'receive_in', 'warehouse': self.warehouse_b.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 1.5 Slice H — Purchase Invoice Posting (backend foundation)
# ══════════════════════════════════════════════════════════════════════════════

class _PurchaseInvoiceTestBase(APITestCase):
    """Two-tenant fixture with supplier, cashbox, payment method, and a
    default purchase_receiving warehouse for tenant A."""

    @classmethod
    def setUpTestData(cls):
        # ── Tenant A ──
        cls.tenant = Tenant.objects.create(name='Purch Tenant A')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='A-Main')
        cls.manager = User.objects.create_user(
            username='pmgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.cashier = User.objects.create_user(
            username='pcsh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Drinks')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Cola', barcode='COLA-1', sku='SKU-COLA',
            price=Decimal('10.00'), cost=Decimal('6.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        cls.supplier = Supplier.objects.create(tenant=cls.tenant, name='Acme Supply')
        cls.cashbox = FinancialAccount.objects.create(
            tenant=cls.tenant, name='Main Cashbox',
            account_type=FinancialAccount.AccountType.CASHBOX,
            opening_balance=Decimal('1000.00'),
        )
        cls.cash_method = PaymentMethod.objects.create(
            tenant=cls.tenant, name='Cash',
            method_type=PaymentMethod.MethodType.CASH,
        )
        cls.warehouse = Warehouse.objects.create(
            tenant=cls.tenant, code='WH-A', name='A Store',
        )
        # Default purchase-receiving link for warehouse auto-resolution.
        cls.recv_link = BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch, warehouse=cls.warehouse,
            role=BranchWarehouse.Role.PURCHASE_RECEIVING,
            is_default=True, is_active=True,
        )

        # ── Tenant B (foreign — for cross-tenant + isolation tests) ──
        cls.tenant_b = Tenant.objects.create(name='Purch Tenant B')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='B-Main')
        cls.supplier_b = Supplier.objects.create(tenant=cls.tenant_b, name='B Supply')
        cls.warehouse_b = Warehouse.objects.create(
            tenant=cls.tenant_b, code='WH-B', name='B Store',
        )
        cls.cashbox_b = FinancialAccount.objects.create(
            tenant=cls.tenant_b, name='B Cashbox',
            account_type=FinancialAccount.AccountType.CASHBOX,
        )
        cls.manager_b = User.objects.create_user(
            username='pmgr_b', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant_b, branch=cls.branch_b,
        )

    def _body(self, **over):
        body = {
            'branch':   self.branch.id,
            'supplier': self.supplier.id,
            'lines': [{
                'product':   self.product.id,
                'warehouse': self.warehouse.id,
                'qty':       '50.000',
                'unit_cost': '9.00',
            }],
        }
        body.update(over)
        return body


class PurchaseInvoicePostingTests(_PurchaseInvoiceTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_cash_purchase_increases_stock_updates_cost_decreases_cashbox(self):
        body = self._body(
            paid_amount='450.00', source_account=self.cashbox.id,
            payment_method=self.cash_method.id,
        )
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['payment_status'], 'paid')
        self.assertEqual(data['total_amount'], '450.00')
        self.assertEqual(data['credit_amount'], '0.00')

        # Stock 100 → 150 in the chosen warehouse.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('150.000'))
        # Moving average: (100*6 + 50*9) / 150 = 7.00
        self.assertEqual(self.product.cost, Decimal('7.00'))

        mv = StockMovement.objects.get(
            source_document_type='purchase_invoice',
            source_document_id=data['id'],
        )
        self.assertEqual(mv.movement_type, StockMovement.MovementType.PURCHASE_IN)
        self.assertEqual(mv.warehouse_id, self.warehouse.id)

        # Cashbox 1000 → 550 (credit 450 leaves the asset account).
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox),
            Decimal('550.00'),
        )
        # No AP movement for a fully-paid purchase.
        self.assertEqual(
            supplier_ap_service.get_supplier_balance(self.supplier),
            Decimal('0.00'),
        )

    def test_credit_purchase_increases_stock_and_supplier_ap(self):
        body = self._body()  # paid_amount defaults to 0 → fully on credit
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['payment_status'], 'unpaid')
        self.assertEqual(data['credit_amount'], '450.00')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('150.000'))

        # Supplier AP 0 → 450 (credit increases the liability).
        self.assertEqual(
            supplier_ap_service.get_supplier_balance(self.supplier),
            Decimal('450.00'),
        )
        # Cashbox untouched.
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox),
            Decimal('1000.00'),
        )

    def test_partial_purchase_creates_finance_and_ap_effects(self):
        body = self._body(paid_amount='200.00', source_account=self.cashbox.id)
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['payment_status'], 'partially_paid')
        self.assertEqual(data['paid_amount'], '200.00')
        self.assertEqual(data['credit_amount'], '250.00')

        # Cashbox 1000 → 800, AP 0 → 250.
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox),
            Decimal('800.00'),
        )
        self.assertEqual(
            supplier_ap_service.get_supplier_balance(self.supplier),
            Decimal('250.00'),
        )

    def test_default_purchase_receiving_warehouse_is_resolved(self):
        # Omit warehouse on the line — service resolves the default link.
        body = self._body(lines=[{
            'product': self.product.id, 'qty': '10.000', 'unit_cost': '5.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        line = PurchaseInvoiceLine.objects.get(purchase_invoice_id=resp.json()['id'])
        self.assertEqual(line.warehouse_id, self.warehouse.id)
        mv = StockMovement.objects.get(
            source_document_type='purchase_invoice',
            source_document_id=resp.json()['id'],
        )
        self.assertEqual(mv.warehouse_id, self.warehouse.id)

    def test_explicit_warehouse_is_accepted(self):
        other = Warehouse.objects.create(tenant=self.tenant, code='WH-A2', name='A2')
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': other.id,
            'qty': '5.000', 'unit_cost': '5.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        line = PurchaseInvoiceLine.objects.get(purchase_invoice_id=resp.json()['id'])
        self.assertEqual(line.warehouse_id, other.id)

    def test_tax_and_discount_stored_in_totals(self):
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '10.000', 'unit_cost': '10.00',
            'discount_amount': '5.00', 'tax_amount': '14.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['subtotal'], '100.00')
        self.assertEqual(data['discount_total'], '5.00')
        self.assertEqual(data['tax_total'], '14.00')
        # total = subtotal - discount + tax = 100 - 5 + 14 = 109
        self.assertEqual(data['total_amount'], '109.00')

    def test_non_stock_line_type_rejected(self):
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '1.000', 'unit_cost': '5.00', 'line_type': 'expense',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paid_amount_over_total_rejected(self):
        body = self._body(paid_amount='500.00', source_account=self.cashbox.id)
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_and_negative_qty_rejected(self):
        for bad in ('0', '-3'):
            body = self._body(lines=[{
                'product': self.product.id, 'warehouse': self.warehouse.id,
                'qty': bad, 'unit_cost': '5.00',
            }])
            resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_cross_tenant_refs_rejected(self):
        for field, value in [
            ('supplier', self.supplier_b.id),
            ('source_account', self.cashbox_b.id),
        ]:
            body = self._body(paid_amount='10.00', source_account=self.cashbox.id)
            body[field] = value
            resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, field)

        # Cross-tenant warehouse on a line.
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse_b.id,
            'qty': '1.000', 'unit_cost': '5.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_post(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(reverse('purchase-invoice-list'),
                                self._body(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_atomic_rollback_when_ap_posting_fails(self):
        """If AP posting raises, the whole document (invoice, lines, stock,
        cost, finance) rolls back — nothing is persisted."""
        invoices_before = PurchaseInvoice.objects.count()
        movements_before = StockMovement.objects.count()

        with patch.object(
            purchase_invoice_service.ap, 'record_supplier_ap_credit',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                purchase_invoice_service.post_purchase_invoice(
                    tenant=self.tenant,
                    branch=self.branch,
                    supplier=self.supplier,
                    lines=[{
                        'product': self.product,
                        'warehouse': self.warehouse,
                        'qty': Decimal('5'),
                        'unit_cost': Decimal('9.00'),
                    }],
                    paid_amount=Decimal('0'),  # fully credit → triggers AP post
                )

        self.assertEqual(PurchaseInvoice.objects.count(), invoices_before)
        self.assertEqual(StockMovement.objects.count(), movements_before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('100.000'))  # unchanged
        self.assertEqual(self.product.cost, Decimal('6.00'))       # unchanged


class PurchaseInvoiceIdempotencyTests(_PurchaseInvoiceTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_replay_returns_original_and_posts_once(self):
        body = self._body(paid_amount='450.00', source_account=self.cashbox.id)
        url = reverse('purchase-invoice-list')

        first = self.client.post(url, body, format='json', HTTP_IDEMPOTENCY_KEY='pi-key-1')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)

        second = self.client.post(url, body, format='json', HTTP_IDEMPOTENCY_KEY='pi-key-1')
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.json()['id'], first.json()['id'])

        # Only one invoice + one stock movement actually posted.
        self.assertEqual(PurchaseInvoice.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(source_document_type='purchase_invoice').count(), 1,
        )

    def test_same_key_different_payload_conflicts(self):
        url = reverse('purchase-invoice-list')
        self.client.post(url, self._body(paid_amount='450.00', source_account=self.cashbox.id),
                         format='json', HTTP_IDEMPOTENCY_KEY='pi-key-2')
        resp = self.client.post(
            url, self._body(),  # different payload (no payment)
            format='json', HTTP_IDEMPOTENCY_KEY='pi-key-2',
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)


class PurchaseInvoiceReadScopingTests(_PurchaseInvoiceTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post(reverse('purchase-invoice-list'),
                                self._body(), format='json')
        self.invoice_id = resp.json()['id']

    def test_list_and_detail_are_tenant_scoped(self):
        # Tenant B manager cannot see tenant A's invoice.
        self.client.force_authenticate(user=self.manager_b)
        listing = self.client.get(reverse('purchase-invoice-list'))
        ids = [r['id'] for r in listing.json()['results']]
        self.assertNotIn(self.invoice_id, ids)

        detail = self.client.get(
            reverse('purchase-invoice-detail', kwargs={'pk': self.invoice_id}),
        )
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)


class LegacyInventoryPurchaseCompatTests(_PurchaseInvoiceTestBase):
    """The legacy POST /api/inventory/purchase/ stays inventory-only and is
    not affected by the new PurchaseInvoice flow."""

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_legacy_purchase_still_increments_stock_without_a_document(self):
        before = self.product.stock
        resp = self.client.post(reverse('inventory-purchase'), {
            'product': self.product.id, 'qty': '20', 'cost_price': '7.50',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, before + Decimal('20'))
        # Legacy path creates no PurchaseInvoice document.
        self.assertEqual(PurchaseInvoice.objects.count(), 0)
