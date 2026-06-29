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

from accounts.models import Branch, Tenant, Terminal, User
from pos.models import (
    BranchWarehouse, Category, Payment, Product, Sale, StockMovement, Warehouse,
)
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
