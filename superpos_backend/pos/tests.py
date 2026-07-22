"""End-to-end tests for the Hyper Fekra Quesna workflows.

Covers:
    * Weight-encoded barcode scanning (Task 1)
    * Sale checkout with amount_paid / change (Task 2)
    * Dynamic receipt layout (Task 3)
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from unittest.mock import patch

from accounts.models import (
    Branch, BranchPaymentMethod, Customer, CustomerARMovement, FinancialAccount,
    FinancialAccountMovement, PaymentMethod, Supplier, Tenant, Terminal, User,
)
from accounts.services import account_movements as account_service
from accounts.services import customer_ar as customer_ar_service
from accounts.services import supplier_ap as supplier_ap_service
from pos.models import (
    AuditLog, BranchWarehouse, Category, Payment, Product, PurchaseInvoice,
    PurchaseInvoiceLine, Sale, SaleItem, StockMovement, Warehouse, WarehouseStock,
)
from pos.services import purchase_invoices as purchase_invoice_service
from pos.services import sale_posting
from pos.services import stock_movements as stock_movement_service
from pos.views import _parse_weight_encoded_barcode


def _grant_default_routing(tenant, branch):
    """Gate A test helper: give a branch the default cash/card/wallet routing.

    Mirrors what the `provision_default_payment_routing` command provisions
    for real legacy branches — under strict routing (GA-2) every completed
    sale must resolve a route, so fixtures must self-serve. Returns the
    accounts keyed by account_type for balance assertions.
    """
    accounts = {}
    for acct_type, name in [
        (FinancialAccount.AccountType.CASHBOX,         'Main Cashbox'),
        (FinancialAccount.AccountType.CARD_SETTLEMENT, 'Card Settlement'),
        (FinancialAccount.AccountType.WALLET,          'Wallet'),
    ]:
        accounts[acct_type] = FinancialAccount.objects.create(
            tenant=tenant, name=f'{name} ({branch.name})', account_type=acct_type,
        )
    for mtype, acct_type in [
        (PaymentMethod.MethodType.CASH,   FinancialAccount.AccountType.CASHBOX),
        (PaymentMethod.MethodType.CARD,   FinancialAccount.AccountType.CARD_SETTLEMENT),
        (PaymentMethod.MethodType.WALLET, FinancialAccount.AccountType.WALLET),
    ]:
        pm = PaymentMethod.objects.create(
            tenant=tenant, name=f'{mtype} ({branch.name})', method_type=mtype,
        )
        BranchPaymentMethod.objects.create(
            tenant=tenant, branch=branch, payment_method=pm,
            destination_account=accounts[acct_type],
            is_default=True, is_active=True,
        )
    return accounts


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
        # GA-2: every completed sale must resolve a payment route.
        _grant_default_routing(cls.tenant, cls.branch)

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
        # GA-2: every completed sale must resolve a payment route.
        _grant_default_routing(cls.tenant, cls.branch)

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
        # Sprint 5 Batch 1: branch-scoped AVCO blends against branch stock
        # (sum of WarehouseStock for the branch's warehouses), not the bare
        # Product.stock counter — this test's fixture product already has
        # 100 units (set directly on Product.stock by setUpTestData, not
        # via a warehouse-attributed movement), so it needs a matching
        # WarehouseStock row for the moving-average math below to see it,
        # exactly as a real purchase would have recorded it.
        WarehouseStock.objects.create(
            tenant=self.tenant, product=self.product, warehouse=self.warehouse,
            quantity=Decimal('100'),
        )
        body = self._body(
            paid_amount='450.00', source_account=self.cashbox.id,
            payment_method=self.cash_method.id,
        )
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-cash-purchase')
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

    def test_sequential_purchases_compound_correctly_via_costing_service(self):
        """Sprint 3 Batch 2 — the Business Owner's worked example, exercised
        end-to-end through the real API (not just the pure function): two
        sequential purchase invoices at different unit costs must blend into
        the correct average, and the InventoryCost/InventoryCostMovement
        audit trail introduced in Batch 1/2 must stay in sync with it."""
        from pos.models import InventoryCost, InventoryCostMovement

        # Start clean: this product already has stock=100/cost=6.00 from the
        # class fixture — reset it to match the owner's own numbers (10kg
        # @500, then 10kg @600) so the assertions read exactly like the
        # worked example.
        self.product.stock = Decimal('0')
        self.product.cost = Decimal('0.00')
        self.product.save(update_fields=['stock', 'cost'])
        InventoryCost.objects.filter(product=self.product).delete()

        body1 = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '10.000', 'unit_cost': '500.00',
        }])
        resp1 = self.client.post(reverse('purchase-invoice-list'), body1, format='json', HTTP_IDEMPOTENCY_KEY='pit-worked-example-1')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED, resp1.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('10.000'))
        self.assertEqual(self.product.cost, Decimal('500.00'))

        body2 = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '10.000', 'unit_cost': '600.00',
        }])
        resp2 = self.client.post(reverse('purchase-invoice-list'), body2, format='json', HTTP_IDEMPOTENCY_KEY='pit-worked-example-2')
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED, resp2.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('20.000'))
        # (10*500 + 10*600) / 20 = 550.00 — matches the owner's worked example.
        self.assertEqual(self.product.cost, Decimal('550.00'))

        inv_cost = InventoryCost.objects.get(product=self.product)
        self.assertEqual(inv_cost.avg_unit_cost, Decimal('550.0000'))

        movements = list(
            InventoryCostMovement.objects.filter(product=self.product).order_by('id')
        )
        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0].avg_cost_before, Decimal('0.0000'))
        self.assertEqual(movements[0].avg_cost_after, Decimal('500.0000'))
        self.assertEqual(movements[0].source_document_type, 'purchase_invoice')
        self.assertEqual(movements[0].source_document_id, resp1.json()['id'])
        self.assertEqual(movements[1].avg_cost_before, Decimal('500.0000'))
        self.assertEqual(movements[1].avg_cost_after, Decimal('550.0000'))
        self.assertEqual(movements[1].source_document_id, resp2.json()['id'])

    def test_credit_purchase_increases_stock_and_supplier_ap(self):
        body = self._body()  # paid_amount defaults to 0 → fully on credit
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-credit-purchase')
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
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-partial-purchase')
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
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-default-wh')
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
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-explicit-wh')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        line = PurchaseInvoiceLine.objects.get(purchase_invoice_id=resp.json()['id'])
        self.assertEqual(line.warehouse_id, other.id)

    def test_tax_and_discount_stored_in_totals(self):
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '10.000', 'unit_cost': '10.00',
            'discount_amount': '5.00', 'tax_amount': '14.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-tax-discount')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['subtotal'], '100.00')
        self.assertEqual(data['discount_total'], '5.00')
        self.assertEqual(data['tax_total'], '14.00')
        # total = subtotal - discount + tax = 100 - 5 + 14 = 109
        self.assertEqual(data['total_amount'], '109.00')

    def test_purchase_discount_nets_out_of_moving_average_cost(self):
        """Hotfix pack (post-Sprint-3 review) — inventory valuation must
        follow the actual acquisition cost, not the gross purchase price.
        1000 gross, 100 supplier discount → the average cost blended into
        InventoryCost must be (1000-100)/10 = 90.00/unit, not 100.00/unit;
        inventory value must reconcile with the AP liability actually
        posted for the same line (both derived from the same net figure)."""
        from pos.models import InventoryCost

        self.product.stock = Decimal('0')
        self.product.cost = Decimal('0.00')
        self.product.save(update_fields=['stock', 'cost'])
        InventoryCost.objects.filter(product=self.product).delete()

        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '10.000', 'unit_cost': '100.00',
            'discount_amount': '100.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-discount-avco')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertEqual(data['subtotal'], '1000.00')
        self.assertEqual(data['discount_total'], '100.00')
        # total = subtotal - discount + tax = 1000 - 100 + 0 = 900 — the AP
        # liability (fully on credit, paid_amount defaults to 0).
        self.assertEqual(data['total_amount'], '900.00')
        self.assertEqual(data['credit_amount'], '900.00')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('10.000'))
        # (1000 - 100) / 10 = 90.00 — NOT 100.00 (the pre-fix gross-price bug).
        self.assertEqual(self.product.cost, Decimal('90.00'))
        inv_cost = InventoryCost.objects.get(product=self.product)
        self.assertEqual(inv_cost.avg_unit_cost, Decimal('90.0000'))

        # Reconciliation: inventory value added (10 * 90.00 = 900.00) must
        # equal the AP liability actually posted for this purchase (900.00)
        # — both are the same net acquisition value, per the hotfix policy.
        inventory_value_added = self.product.stock * self.product.cost
        self.assertEqual(inventory_value_added, Decimal('900.00'))
        self.assertEqual(
            supplier_ap_service.get_supplier_balance(self.supplier),
            Decimal('900.00'),
        )

    def test_non_stock_line_type_rejected(self):
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse.id,
            'qty': '1.000', 'unit_cost': '5.00', 'line_type': 'expense',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-non-stock-rejected')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paid_amount_over_total_rejected(self):
        body = self._body(paid_amount='500.00', source_account=self.cashbox.id)
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-paid-over-total')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_and_negative_qty_rejected(self):
        for bad in ('0', '-3'):
            body = self._body(lines=[{
                'product': self.product.id, 'warehouse': self.warehouse.id,
                'qty': bad, 'unit_cost': '5.00',
            }])
            resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-zero-neg-qty')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_cross_tenant_refs_rejected(self):
        for field, value in [
            ('supplier', self.supplier_b.id),
            ('source_account', self.cashbox_b.id),
        ]:
            body = self._body(paid_amount='10.00', source_account=self.cashbox.id)
            body[field] = value
            resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-cross-tenant')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, field)

        # Cross-tenant warehouse on a line.
        body = self._body(lines=[{
            'product': self.product.id, 'warehouse': self.warehouse_b.id,
            'qty': '1.000', 'unit_cost': '5.00',
        }])
        resp = self.client.post(reverse('purchase-invoice-list'), body, format='json', HTTP_IDEMPOTENCY_KEY='pit-cross-tenant-wh')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_cannot_post(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.post(reverse('purchase-invoice-list'),
                                self._body(), format='json',
                                HTTP_IDEMPOTENCY_KEY='pit-cashier-forbidden')
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
                                self._body(), format='json',
                                HTTP_IDEMPOTENCY_KEY='read-scoping-setup')
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


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 1.5 Slice I — Sales / POS Posting Ledger Integration
# ══════════════════════════════════════════════════════════════════════════════

class _SalePostingTestBase(APITestCase):
    """Tenant A is fully configured (routing + sales warehouse); tenant B is
    left unconfigured for cross-tenant + legacy-fallback tests."""

    @classmethod
    def setUpTestData(cls):
        # ── Tenant A (configured) ──
        cls.tenant = Tenant.objects.create(name='Sale Tenant A')
        cls.branch = Branch.objects.create(tenant=cls.tenant, name='A-Main')
        cls.cashier = User.objects.create_user(
            username='scsh_a', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.manager = User.objects.create_user(
            username='smgr_a', password='pw', role=User.Role.MANAGER,
            tenant=cls.tenant, branch=cls.branch,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Drinks')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Cola', barcode='COLA-S1', sku='SKU-COLA-S',
            price=Decimal('10.00'), cost=Decimal('6.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        cls.customer = Customer.objects.create(tenant=cls.tenant, name='Walk-in Co')

        # Financial accounts (asset-like; opening balance 0).
        cls.cashbox = FinancialAccount.objects.create(
            tenant=cls.tenant, name='Cashbox',
            account_type=FinancialAccount.AccountType.CASHBOX)
        cls.card_acct = FinancialAccount.objects.create(
            tenant=cls.tenant, name='Card Settlement',
            account_type=FinancialAccount.AccountType.CARD_SETTLEMENT)
        cls.wallet_acct = FinancialAccount.objects.create(
            tenant=cls.tenant, name='Wallet',
            account_type=FinancialAccount.AccountType.WALLET)

        # Payment methods + branch routing.
        for mtype, acct in [
            (PaymentMethod.MethodType.CASH, cls.cashbox),
            (PaymentMethod.MethodType.CARD, cls.card_acct),
            (PaymentMethod.MethodType.WALLET, cls.wallet_acct),
        ]:
            pm = PaymentMethod.objects.create(
                tenant=cls.tenant, name=f'{mtype}-pm', method_type=mtype)
            BranchPaymentMethod.objects.create(
                tenant=cls.tenant, branch=cls.branch, payment_method=pm,
                destination_account=acct, is_default=True, is_active=True)

        # Sales warehouse + default sales link.
        cls.warehouse = Warehouse.objects.create(
            tenant=cls.tenant, code='WH-SA', name='A Sales Store')
        BranchWarehouse.objects.create(
            tenant=cls.tenant, branch=cls.branch, warehouse=cls.warehouse,
            role=BranchWarehouse.Role.SALES, is_default=True, is_active=True)

        # ── Tenant B (unconfigured — for cross-tenant + legacy fallback) ──
        cls.tenant_b = Tenant.objects.create(name='Sale Tenant B')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant_b, name='B-Main')
        cls.cashier_b = User.objects.create_user(
            username='scsh_b', password='pw', role=User.Role.CASHIER,
            tenant=cls.tenant_b, branch=cls.branch_b,
        )
        cls.category_b = Category.objects.create(tenant=cls.tenant_b, name='B-Cat')
        cls.product_b = Product.objects.create(
            tenant=cls.tenant_b, category=cls.category_b,
            name='B-Cola', barcode='COLA-B1', sku='SKU-COLA-B',
            price=Decimal('10.00'), cost=Decimal('6.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        cls.customer_b = Customer.objects.create(tenant=cls.tenant_b, name='B Cust')
        cls.warehouse_b = Warehouse.objects.create(
            tenant=cls.tenant_b, code='WH-SB', name='B Store')

    def _sale_body(self, method='cash', **over):
        body = {
            'items': [{'product': self.product.id, 'qty': '2', 'price_each': '10.00'}],
            'method': method,
            'amount_paid': '20.00',
        }
        body.update(over)
        return body


class SalePostingTests(_SalePostingTestBase):

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def test_cash_sale_decreases_stock_and_increases_cashbox(self):
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('98.000'))

        sale_id = resp.json()['id']
        mv = StockMovement.objects.get(source_document_type='sale', source_document_id=sale_id)
        self.assertEqual(mv.movement_type, StockMovement.MovementType.SALE_OUT)
        self.assertEqual(mv.warehouse_id, self.warehouse.id)

        # Cashbox (asset) debit → balance up by the 20.00 total.
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('20.00'))

    def test_card_sale_routes_to_card_settlement(self):
        resp = self.client.post(reverse('sale-list'), self._sale_body('card'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            account_service.get_account_current_balance(self.card_acct), Decimal('20.00'))
        # Cashbox untouched.
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('0.00'))

    def test_wallet_sale_routes_to_wallet_account(self):
        resp = self.client.post(reverse('sale-list'), self._sale_body('wallet'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            account_service.get_account_current_balance(self.wallet_acct), Decimal('20.00'))

    def test_credit_sale_requires_customer(self):
        body = self._sale_body('credit')   # no customer
        body.pop('amount_paid')
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_credit_sale_increases_customer_ar(self):
        body = self._sale_body('credit', customer=self.customer.id)
        body.pop('amount_paid')  # nothing tendered now
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        # Customer AR (asset) debit → owes the 20.00 total.
        self.assertEqual(
            customer_ar_service.get_customer_balance(self.customer), Decimal('20.00'))
        # Stock still leaves; no cashbox movement.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('98.000'))
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('0.00'))

    def test_default_sales_warehouse_is_resolved(self):
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        sale_id = resp.json()['id']
        item = SaleItem.objects.get(sale_id=sale_id)
        self.assertEqual(item.warehouse_id, self.warehouse.id)
        self.assertEqual(item.unit_cost, Decimal('6.00'))  # cost snapshot

    def test_explicit_line_warehouse_is_accepted(self):
        other = Warehouse.objects.create(tenant=self.tenant, code='WH-SA2', name='A2')
        body = self._sale_body('cash')
        body['items'][0]['warehouse'] = other.id
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        item = SaleItem.objects.get(sale_id=resp.json()['id'])
        self.assertEqual(item.warehouse_id, other.id)

    def test_cross_tenant_product_rejected(self):
        body = self._sale_body('cash')
        body['items'][0]['product'] = self.product_b.id
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_customer_rejected(self):
        body = self._sale_body('credit', customer=self.customer_b.id)
        body.pop('amount_paid')
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_warehouse_rejected(self):
        body = self._sale_body('cash')
        body['items'][0]['warehouse'] = self.warehouse_b.id
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversell_still_allowed_with_warning(self):
        self.product.stock = Decimal('0')
        self.product.save(update_fields=['stock'])
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(resp.json()['warnings'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('-2.000'))

    def test_atomic_rollback_when_finance_posting_fails(self):
        sales_before = Sale.objects.count()
        moves_before = StockMovement.objects.count()
        with patch.object(
            sale_posting.fa, 'record_account_debit',
            side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')

        self.assertEqual(Sale.objects.count(), sales_before)
        self.assertEqual(StockMovement.objects.count(), moves_before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('100.000'))
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('0.00'))

    def test_warehouse_is_traceability_only_global_stock_is_shared(self):
        """SaleItem.warehouse / StockMovement.warehouse record WHERE stock left
        (traceability), but there is no per-warehouse balance yet: sales from
        two different sales warehouses both decrement the single global
        Product.stock. Per-warehouse balances are a deferred slice."""
        wh2 = Warehouse.objects.create(tenant=self.tenant, code='WH-SA3', name='A3')

        # Sale 1 from the branch's default sales warehouse.
        r1 = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)

        # Sale 2 from an explicit, different warehouse.
        body = self._sale_body('cash')
        body['items'][0]['warehouse'] = wh2.id
        r2 = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)

        # Each movement is tagged with its own warehouse (traceability).
        mv1 = StockMovement.objects.get(
            source_document_id=r1.json()['id'], source_document_type='sale')
        mv2 = StockMovement.objects.get(
            source_document_id=r2.json()['id'], source_document_type='sale')
        self.assertEqual(mv1.warehouse_id, self.warehouse.id)
        self.assertEqual(mv2.warehouse_id, wh2.id)

        # But on-hand is a single global counter: 100 - 2 - 2 = 96 (NOT split
        # per warehouse). This asserts the deferred-balance contract.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('96.000'))


class SalePostingHardeningTests(_SalePostingTestBase):
    """GA-2 strict routing: no sale may silently skip ledger posting. A
    missing or inactive route for the chosen method is a 400 + full rollback —
    including branches with zero BranchPaymentMethod rows (the legacy
    best-effort skip was removed)."""

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _assert_nothing_persisted(self, sales_before, moves_before):
        self.assertEqual(Sale.objects.count(), sales_before)
        self.assertEqual(StockMovement.objects.count(), moves_before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('100.000'))
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('0.00'))

    def test_configured_branch_inactive_route_returns_400_and_rolls_back(self):
        # Deactivate the cash route on an otherwise-configured branch.
        BranchPaymentMethod.objects.filter(
            tenant=self.tenant, branch=self.branch,
            payment_method__method_type=PaymentMethod.MethodType.CASH,
        ).update(is_active=False)

        sales_before = Sale.objects.count()
        moves_before = StockMovement.objects.count()
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self._assert_nothing_persisted(sales_before, moves_before)

    def test_configured_branch_missing_route_returns_400_and_rolls_back(self):
        # Remove the cash route entirely; the branch still has card + wallet, so
        # it is "configured" and a cash sale must not silently skip.
        BranchPaymentMethod.objects.filter(
            tenant=self.tenant, branch=self.branch,
            payment_method__method_type=PaymentMethod.MethodType.CASH,
        ).delete()

        sales_before = Sale.objects.count()
        moves_before = StockMovement.objects.count()
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self._assert_nothing_persisted(sales_before, moves_before)

    def test_unrouted_branch_sale_fails_with_structured_error(self):
        """GA-2: replaces `test_legacy_branch_skips_posting_but_warns` — the
        legacy silent-skip was removed; a branch with zero BranchPaymentMethod
        rows now fails the sale atomically with a stable error code."""
        self.client.force_authenticate(user=self.cashier_b)
        body = {
            'items': [{'product': self.product_b.id, 'qty': '2', 'price_each': '10.00'}],
            'method': 'cash', 'amount_paid': '20.00',
        }
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

        data = resp.json()
        self.assertIn('payment_routing_missing', data['code'])
        self.assertIn('No active payment routing', data['payment'][0])

        # Full rollback — nothing persisted for tenant B.
        self.assertEqual(Sale.objects.filter(tenant=self.tenant_b).count(), 0)
        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant_b).count(), 0)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.stock, Decimal('100.000'))
        self.assertEqual(
            FinancialAccountMovement.objects.filter(tenant=self.tenant_b).count(), 0)

    def test_posting_error_has_structured_shape(self):
        # GA-8: the 400 body carries the legacy `payment` display key (as a
        # list) plus stable machine-readable `code` / `field` / `detail` keys.
        BranchPaymentMethod.objects.filter(
            tenant=self.tenant, branch=self.branch,
            payment_method__method_type=PaymentMethod.MethodType.CASH,
        ).update(is_active=False)

        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        body = resp.json()
        self.assertIsInstance(body.get('payment'), list)
        self.assertTrue(body['payment'][0])
        self.assertIn('payment_routing_missing', body['code'])
        self.assertIn('method', body['field'])
        self.assertTrue(body.get('detail'))


class GateADefaultRouteUniquenessTests(_SalePostingTestBase):
    """GA-6: at most one active default route per (branch, method_type); the
    resolver stays deterministic even for pre-gate bad data."""

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_second_active_default_of_same_method_type_is_rejected(self):
        second_pm = PaymentMethod.objects.create(
            tenant=self.tenant, name='Cash Drawer 2',
            method_type=PaymentMethod.MethodType.CASH)
        resp = self.client.post(
            reverse('branch-payment-method-list', kwargs={'branch_pk': self.branch.pk}),
            {
                'payment_method': second_pm.id,
                'destination_account': self.cashbox.id,
                'is_default': True,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('is_default', resp.json())

    def test_second_route_of_same_type_allowed_when_not_default(self):
        second_pm = PaymentMethod.objects.create(
            tenant=self.tenant, name='Cash Drawer 2',
            method_type=PaymentMethod.MethodType.CASH)
        resp = self.client.post(
            reverse('branch-payment-method-list', kwargs={'branch_pk': self.branch.pk}),
            {
                'payment_method': second_pm.id,
                'destination_account': self.cashbox.id,
                'is_default': False,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_demoting_the_existing_default_then_promoting_another_is_allowed(self):
        # The guard must not block the legitimate two-step swap flow.
        existing = BranchPaymentMethod.objects.get(
            tenant=self.tenant, branch=self.branch,
            payment_method__method_type=PaymentMethod.MethodType.CASH)
        resp = self.client.patch(
            reverse('branch-payment-method-detail',
                    kwargs={'branch_pk': self.branch.pk, 'pk': existing.pk}),
            {'is_default': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

        second_pm = PaymentMethod.objects.create(
            tenant=self.tenant, name='Cash Drawer 2',
            method_type=PaymentMethod.MethodType.CASH)
        resp = self.client.post(
            reverse('branch-payment-method-list', kwargs={'branch_pk': self.branch.pk}),
            {
                'payment_method': second_pm.id,
                'destination_account': self.cashbox.id,
                'is_default': True,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_resolver_is_deterministic_for_bad_legacy_data(self):
        """Two active defaults (pre-gate bad data, bypassing the serializer)
        resolve to the newest row, not arbitrary DB order."""
        second_pm = PaymentMethod.objects.create(
            tenant=self.tenant, name='Cash Drawer 2',
            method_type=PaymentMethod.MethodType.CASH)
        newest = BranchPaymentMethod.objects.create(
            tenant=self.tenant, branch=self.branch, payment_method=second_pm,
            destination_account=self.cashbox, is_default=True, is_active=True)

        resolved = sale_posting.resolve_branch_payment_method(
            tenant=self.tenant, branch=self.branch, method='cash')
        self.assertEqual(resolved.pk, newest.pk)


class SaleLegacyAndScopingTests(_SalePostingTestBase):

    def test_unconfigured_tenant_sale_fails_and_rolls_back(self):
        """GA-2: replaces `test_unconfigured_tenant_sale_still_posts_without_
        ledger` — tenant B has no BranchPaymentMethod, so the sale now fails
        atomically instead of posting without a GL row."""
        self.client.force_authenticate(user=self.cashier_b)
        body = {
            'items': [{'product': self.product_b.id, 'qty': '2', 'price_each': '10.00'}],
            'method': 'cash', 'amount_paid': '20.00',
        }
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertIn('payment_routing_missing', resp.json()['code'])

        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.stock, Decimal('100.000'))
        self.assertEqual(Sale.objects.filter(tenant=self.tenant_b).count(), 0)
        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant_b).count(), 0)
        self.assertEqual(
            FinancialAccountMovement.objects.filter(tenant=self.tenant_b).count(), 0)

    def test_list_is_tenant_scoped(self):
        self.client.force_authenticate(user=self.cashier)
        sale_id = self.client.post(
            reverse('sale-list'), self._sale_body('cash'), format='json').json()['id']

        # Tenant B manager-less cashier cannot see tenant A's sale.
        self.client.force_authenticate(user=self.cashier_b)
        listing = self.client.get(reverse('sale-list'))
        ids = [r['id'] for r in listing.json()['results']]
        self.assertNotIn(sale_id, ids)


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 1.5 Slice J — Per-Warehouse Stock Balance (WarehouseStock)
# ══════════════════════════════════════════════════════════════════════════════

class WarehouseStockServiceTests(APITestCase):
    """Service-layer tests for the cached per-warehouse balance."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='WHS Tenant A')
        cls.category = Category.objects.create(tenant=cls.tenant, name='Cat')
        cls.product = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Widget', barcode='W-1', sku='SKU-W',
            price=Decimal('10.00'), cost=Decimal('5.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('0'),
        )
        cls.wh1 = Warehouse.objects.create(tenant=cls.tenant, code='WH1', name='Store 1')
        cls.wh2 = Warehouse.objects.create(tenant=cls.tenant, code='WH2', name='Store 2')
        cls.tenant_b = Tenant.objects.create(name='WHS Tenant B')
        cls.wh_b = Warehouse.objects.create(tenant=cls.tenant_b, code='WHB', name='B Store')

    def _in(self, wh, qty):
        return stock_movement_service.record_stock_in(
            product=self.product, quantity=qty,
            movement_type=StockMovement.MovementType.RECEIVE_IN, warehouse=wh,
        )

    def _out(self, wh, qty):
        return stock_movement_service.record_stock_out(
            product=self.product, quantity=qty,
            movement_type=StockMovement.MovementType.SALE_OUT, warehouse=wh,
        )

    def test_stock_in_creates_and_increments_row(self):
        self._in(self.wh1, Decimal('10'))
        ws = WarehouseStock.objects.get(product=self.product, warehouse=self.wh1)
        self.assertEqual(ws.quantity, Decimal('10.000'))

    def test_repeated_movements_accumulate_in_one_row(self):
        self._in(self.wh1, Decimal('10'))
        self._in(self.wh1, Decimal('5'))
        self._out(self.wh1, Decimal('4'))
        rows = WarehouseStock.objects.filter(product=self.product, warehouse=self.wh1)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().quantity, Decimal('11.000'))  # 10 + 5 - 4

    def test_separate_warehouses_have_independent_balances(self):
        self._in(self.wh1, Decimal('10'))
        self._in(self.wh2, Decimal('3'))
        self.assertEqual(
            WarehouseStock.objects.get(product=self.product, warehouse=self.wh1).quantity,
            Decimal('10.000'))
        self.assertEqual(
            WarehouseStock.objects.get(product=self.product, warehouse=self.wh2).quantity,
            Decimal('3.000'))
        # Global Product.stock is the single shared counter (sum of the two).
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('13.000'))

    def test_warehouse_none_updates_product_only_no_row(self):
        self._in(None, Decimal('7'))
        self.assertEqual(WarehouseStock.objects.filter(product=self.product).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('7.000'))

    def test_cross_tenant_warehouse_rejected(self):
        with self.assertRaises(stock_movement_service.StockMovementError):
            self._in(self.wh_b, Decimal('5'))
        self.assertEqual(WarehouseStock.objects.filter(warehouse=self.wh_b).count(), 0)

    def test_oversell_allows_negative_warehouse_balance(self):
        self._in(self.wh1, Decimal('2'))
        self._out(self.wh1, Decimal('5'))
        ws = WarehouseStock.objects.get(product=self.product, warehouse=self.wh1)
        self.assertEqual(ws.quantity, Decimal('-3.000'))

    def test_direct_apply_warehouse_delta_is_noop_for_none(self):
        result = stock_movement_service.apply_warehouse_delta(
            product=self.product, warehouse=None, delta=Decimal('5'))
        self.assertIsNone(result)
        self.assertEqual(WarehouseStock.objects.count(), 0)

    def test_cached_matches_movement_derived_balance(self):
        self._in(self.wh1, Decimal('10'))
        self._in(self.wh2, Decimal('4'))
        self._out(self.wh1, Decimal('3'))
        for wh in (self.wh1, self.wh2):
            cached = WarehouseStock.objects.get(product=self.product, warehouse=wh).quantity
            derived = stock_movement_service.get_product_stock_balance(self.product, warehouse=wh)
            self.assertEqual(cached, derived)

    def test_sum_of_warehouse_stock_reconciles_with_product_stock(self):
        from django.db.models import Sum
        self._in(self.wh1, Decimal('10'))
        self._in(self.wh2, Decimal('4'))
        self._out(self.wh1, Decimal('3'))
        total = (WarehouseStock.objects.filter(product=self.product)
                 .aggregate(s=Sum('quantity'))['s'])
        self.product.refresh_from_db()
        self.assertEqual(total, self.product.stock)  # all movements carried a warehouse


class WarehouseStockPurchaseTests(_PurchaseInvoiceTestBase):
    """The purchase-invoice posting path feeds the receiving warehouse."""

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_purchase_invoice_increments_receiving_warehouse_stock(self):
        resp = self.client.post(reverse('purchase-invoice-list'), self._body(), format='json',
                                 HTTP_IDEMPOTENCY_KEY='pit-warehouse-stock-increment')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        ws = WarehouseStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(ws.quantity, Decimal('50.000'))


class WarehouseStockSaleAndApiTests(_SalePostingTestBase):
    """Sale, void, and the read-only WarehouseStock endpoints (tenant A is
    fully configured with a default sales warehouse)."""

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _seed(self, warehouse, qty):
        stock_movement_service.record_stock_in(
            product=self.product, quantity=qty,
            movement_type=StockMovement.MovementType.RECEIVE_IN, warehouse=warehouse,
        )

    def test_cash_sale_decrements_default_sales_warehouse(self):
        self._seed(self.warehouse, Decimal('50'))
        resp = self.client.post(reverse('sale-list'), self._sale_body('cash'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        ws = WarehouseStock.objects.get(product=self.product, warehouse=self.warehouse)
        self.assertEqual(ws.quantity, Decimal('48.000'))  # 50 - 2

    def test_explicit_warehouse_sale_decrements_that_warehouse_only(self):
        other = Warehouse.objects.create(tenant=self.tenant, code='WH-EXP', name='Exp')
        self._seed(other, Decimal('20'))
        body = self._sale_body('cash')
        body['items'][0]['warehouse'] = other.id
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(
            WarehouseStock.objects.get(product=self.product, warehouse=other).quantity,
            Decimal('18.000'))
        # Default sales warehouse untouched.
        self.assertFalse(
            WarehouseStock.objects.filter(product=self.product, warehouse=self.warehouse).exists())

    def test_unconfigured_tenant_sale_fails_and_creates_no_warehouse_stock(self):
        # GA-2: the unrouted tenant B sale fails outright (see the strict
        # routing tests); trivially no WarehouseStock row may appear either.
        self.client.force_authenticate(user=self.cashier_b)
        body = {
            'items': [{'product': self.product_b.id, 'qty': '2', 'price_each': '10.00'}],
            'method': 'cash', 'amount_paid': '20.00',
        }
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertEqual(WarehouseStock.objects.filter(tenant=self.tenant_b).count(), 0)

    def test_void_restores_warehouse_stock(self):
        self._seed(self.warehouse, Decimal('10'))
        sale_id = self.client.post(
            reverse('sale-list'), self._sale_body('cash'), format='json').json()['id']
        self.assertEqual(
            WarehouseStock.objects.get(product=self.product, warehouse=self.warehouse).quantity,
            Decimal('8.000'))
        void = self.client.post(reverse('sale-void-pk', args=[sale_id]))
        self.assertEqual(void.status_code, status.HTTP_200_OK, void.content)
        self.assertEqual(
            WarehouseStock.objects.get(product=self.product, warehouse=self.warehouse).quantity,
            Decimal('10.000'))

    def test_list_endpoint_is_manager_only_and_tenant_scoped(self):
        self._seed(self.warehouse, Decimal('5'))
        # Cashier is below Manager → 403.
        self.assertEqual(
            self.client.get(reverse('warehouse-stock-list')).status_code,
            status.HTTP_403_FORBIDDEN)
        # Manager → 200, sees the tenant's row.
        self.client.force_authenticate(user=self.manager)
        r = self.client.get(reverse('warehouse-stock-list'))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        rows = r.json()['results']
        self.assertTrue(any(row['warehouse'] == self.warehouse.id for row in rows))

    def test_list_endpoint_is_read_only(self):
        self.client.force_authenticate(user=self.manager)
        r = self.client.post(reverse('warehouse-stock-list'), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_product_and_warehouse_scoped_endpoints(self):
        self._seed(self.warehouse, Decimal('9'))
        self.client.force_authenticate(user=self.manager)
        r1 = self.client.get(reverse('product-warehouse-stock', args=[self.product.id]))
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertTrue(any(
            row['warehouse'] == self.warehouse.id for row in r1.json()['results']))
        r2 = self.client.get(reverse('warehouse-inventory', args=[self.warehouse.id]))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(any(
            row['product'] == self.product.id for row in r2.json()['results']))


class ProductWarehouseStocksRouteTests(_SalePostingTestBase):
    """Gate A component GA-10: the per-product balances endpoint lives at the
    plural path `/api/products/{pk}/warehouse-stocks/` — the exact path the
    frontend calls (superpos/src/api/erp.ts). Pure route rename; the view,
    its permissions, and tenant scoping are unchanged."""

    def _seed(self, warehouse, qty):
        stock_movement_service.record_stock_in(
            product=self.product, quantity=qty,
            movement_type=StockMovement.MovementType.RECEIVE_IN, warehouse=warehouse,
        )

    def test_plural_path_resolves_to_view_and_matches_reverse(self):
        from django.urls import resolve
        from pos.views import ProductWarehouseStockView

        match = resolve(f'/api/products/{self.product.id}/warehouse-stocks/')
        self.assertIs(match.func.view_class, ProductWarehouseStockView)
        self.assertEqual(
            reverse('product-warehouse-stock', args=[self.product.id]),
            f'/api/products/{self.product.id}/warehouse-stocks/',
        )

    def test_authorized_manager_gets_expected_balances_on_plural_path(self):
        self._seed(self.warehouse, Decimal('9'))
        self.client.force_authenticate(user=self.manager)
        resp = self.client.get(f'/api/products/{self.product.id}/warehouse-stocks/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        rows = resp.json()['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product'], self.product.id)
        self.assertEqual(rows[0]['warehouse'], self.warehouse.id)
        self.assertEqual(Decimal(rows[0]['quantity']), Decimal('9.000'))

    def test_cashier_below_manager_is_still_forbidden(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.get(f'/api/products/{self.product.id}/warehouse-stocks/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_tenants_data_is_not_exposed(self):
        self._seed(self.warehouse, Decimal('9'))  # tenant A rows exist
        manager_b = User.objects.create_user(
            username='smgr_b_ga10', password='pw', role=User.Role.MANAGER,
            tenant=self.tenant_b, branch=self.branch_b,
        )
        self.client.force_authenticate(user=manager_b)
        # Tenant B asking for tenant A's product id must see nothing.
        resp = self.client.get(f'/api/products/{self.product.id}/warehouse-stocks/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['results'], [])

    def test_old_singular_path_no_longer_routes(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.get(f'/api/products/{self.product.id}/warehouse-stock/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ══════════════════════════════════════════════════════════════════════════════
#  Release Gate A — sales financial integrity (Sprint 1 Batch 2)
# ══════════════════════════════════════════════════════════════════════════════

class GateAVoidReversalTests(_SalePostingTestBase):
    """GA-7: void must be financially correct — compensating GL/AR reversal
    rows under row lock, original rows preserved, no double-reverse, optional
    reason audited, tenant-scoped, idempotent on retry."""

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def _post_sale(self, method='cash', **over):
        body = self._sale_body(method, **over)
        if method == 'credit':
            body.pop('amount_paid', None)
        resp = self.client.post(reverse('sale-list'), body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        return resp.json()['id']

    def _account_for(self, method):
        return {
            'cash': self.cashbox, 'card': self.card_acct, 'wallet': self.wallet_acct,
        }[method]

    def _assert_finance_void(self, method):
        account = self._account_for(method)
        sale_id = self._post_sale(method)
        self.assertEqual(
            account_service.get_account_current_balance(account), Decimal('20.00'))

        void = self.client.post(reverse('sale-void-pk', args=[sale_id]),
                                {'reason': 'customer changed mind'}, format='json')
        self.assertEqual(void.status_code, status.HTTP_200_OK, void.content)

        # Balance reversed; both rows (original debit + compensating credit) kept.
        self.assertEqual(
            account_service.get_account_current_balance(account), Decimal('0.00'))
        rows = FinancialAccountMovement.objects.filter(account=account).order_by('id')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows[0].debit,  Decimal('20.00'))
        self.assertEqual(rows[1].credit, Decimal('20.00'))
        self.assertEqual(rows[1].movement_type,
                         FinancialAccountMovement.MovementType.SALES_RETURN_OUT)
        self.assertEqual(rows[1].source_document_type, 'sale_void')
        self.assertEqual(rows[1].source_document_id, sale_id)
        # Reversal rows stay inside the sale's tenant.
        self.assertEqual(rows[1].tenant_id, self.tenant.id)

        # Stock restored.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('100.000'))

        # Response carries the reversal references.
        body = void.json()['void']
        self.assertFalse(body['legacy_no_financial_movement'])
        self.assertEqual(len(body['finance_reversals']), 1)
        self.assertEqual(body['reason'], 'customer changed mind')

        # AuditLog entry with actor + reason.
        log = AuditLog.objects.get(model_name='sale', object_id=sale_id)
        self.assertEqual(log.action, AuditLog.Action.VOID)
        self.assertEqual(log.tenant_id, self.tenant.id)
        self.assertEqual(log.user_id, self.cashier.id)
        self.assertEqual(log.reason, 'customer changed mind')

    def test_void_cash_sale_reverses_cashbox_and_stock(self):
        self._assert_finance_void('cash')

    def test_void_card_sale_reverses_card_settlement_and_stock(self):
        self._assert_finance_void('card')

    def test_void_wallet_sale_reverses_wallet_and_stock(self):
        self._assert_finance_void('wallet')

    def test_void_credit_sale_reverses_customer_ar_and_stock(self):
        sale_id = self._post_sale('credit', customer=self.customer.id)
        self.assertEqual(
            customer_ar_service.get_customer_balance(self.customer), Decimal('20.00'))

        void = self.client.post(reverse('sale-void-pk', args=[sale_id]))
        self.assertEqual(void.status_code, status.HTTP_200_OK, void.content)

        self.assertEqual(
            customer_ar_service.get_customer_balance(self.customer), Decimal('0.00'))
        rows = CustomerARMovement.objects.filter(customer=self.customer).order_by('id')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows[1].credit, Decimal('20.00'))
        self.assertEqual(rows[1].movement_type,
                         CustomerARMovement.MovementType.SALES_RETURN)
        self.assertEqual(rows[1].source_document_type, 'sale_void')
        self.assertEqual(rows[1].tenant_id, self.tenant.id)
        self.assertEqual(len(void.json()['void']['ar_reversals']), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('100.000'))

    def test_void_legacy_sale_without_financial_movement_does_not_crash(self):
        """A pre-gate sale that never posted a GL row voids gracefully:
        stock is restored, no reversal row is invented, response is flagged."""
        sale = Sale.objects.create(
            tenant=self.tenant, branch=self.branch, cashier=self.cashier,
            subtotal=Decimal('20.00'), tax_amount=Decimal('0.00'),
            total=Decimal('20.00'), method='cash',
            paid=Decimal('20.00'), change=Decimal('0.00'),
        )
        SaleItem.objects.create(
            sale=sale, product=self.product, product_name=self.product.name,
            barcode=self.product.barcode or '', qty=Decimal('2'),
            price_each=Decimal('10.00'), line_total=Decimal('20.00'),
            unit_cost=Decimal('6.00'),
        )

        void = self.client.post(reverse('sale-void-pk', args=[sale.id]))
        self.assertEqual(void.status_code, status.HTTP_200_OK, void.content)
        body = void.json()['void']
        self.assertTrue(body['legacy_no_financial_movement'])
        self.assertEqual(body['finance_reversals'], [])
        self.assertEqual(FinancialAccountMovement.objects.count(), 0)
        # Stock restored (+2 over the fixture's 100 — the legacy sale row
        # never deducted through the API in this synthetic setup).
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('102.000'))

    def test_second_void_returns_400_and_does_not_double_reverse(self):
        sale_id = self._post_sale('cash')
        first = self.client.post(reverse('sale-void-pk', args=[sale_id]))
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(reverse('sale-void-pk', args=[sale_id]))
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

        # Exactly one reversal row; balance stays reversed once.
        self.assertEqual(
            FinancialAccountMovement.objects.filter(
                source_document_type='sale_void', source_document_id=sale_id,
            ).count(), 1)
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('0.00'))

    def test_repeated_void_with_same_idempotency_key_replays(self):
        sale_id = self._post_sale('cash')
        url = reverse('sale-void-pk', args=[sale_id])

        r1 = self.client.post(url, {}, format='json', HTTP_IDEMPOTENCY_KEY='void-k1')
        self.assertEqual(r1.status_code, status.HTTP_200_OK, r1.content)
        r2 = self.client.post(url, {}, format='json', HTTP_IDEMPOTENCY_KEY='void-k1')
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.content)
        self.assertEqual(r1.json(), r2.json())

        # Replay, not re-processing: still exactly one reversal.
        self.assertEqual(
            FinancialAccountMovement.objects.filter(
                source_document_type='sale_void', source_document_id=sale_id,
            ).count(), 1)

    def test_void_is_tenant_scoped(self):
        """A user from another tenant cannot see — let alone void — the sale."""
        sale_id = self._post_sale('cash')

        self.client.force_authenticate(user=self.cashier_b)
        resp = self.client.post(reverse('sale-void-pk', args=[sale_id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # Tenant A's sale is untouched — still completed, no reversal rows.
        sale = Sale.objects.get(pk=sale_id)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(
            FinancialAccountMovement.objects.filter(
                source_document_type='sale_void', source_document_id=sale_id,
            ).count(), 0)
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('20.00'))


class GateASaleIdempotencyTests(_SalePostingTestBase):
    """Slice 2: POST /sales/ honors the Idempotency-Key header exactly like
    purchase invoices — replay on same payload, 409 on mismatch, tenant-scoped."""

    def setUp(self):
        self.client.force_authenticate(user=self.cashier)

    def test_same_key_same_payload_replays_without_second_sale(self):
        body = self._sale_body('cash')
        r1 = self.client.post(reverse('sale-list'), body, format='json',
                              HTTP_IDEMPOTENCY_KEY='sale-k1')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)
        r2 = self.client.post(reverse('sale-list'), body, format='json',
                              HTTP_IDEMPOTENCY_KEY='sale-k1')
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 1)
        # Stock deducted exactly once; ledger posted exactly once.
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal('98.000'))
        self.assertEqual(
            account_service.get_account_current_balance(self.cashbox), Decimal('20.00'))

    def test_same_key_different_payload_conflicts_409(self):
        r1 = self.client.post(reverse('sale-list'), self._sale_body('cash'),
                              format='json', HTTP_IDEMPOTENCY_KEY='sale-k2')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        other = self._sale_body('cash')
        other['items'][0]['qty'] = '3'
        other['amount_paid'] = '30.00'
        r2 = self.client.post(reverse('sale-list'), other, format='json',
                              HTTP_IDEMPOTENCY_KEY='sale-k2')
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r2.json()['error']['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 1)

    def test_no_key_processes_normally(self):
        for _ in range(2):
            resp = self.client.post(
                reverse('sale-list'), self._sale_body('cash'), format='json')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 2)

    def test_idempotency_keys_are_tenant_scoped(self):
        """The same opaque key used by two tenants must not collide: tenant B
        gets its own processing, never a replay of tenant A's response."""
        r1 = self.client.post(reverse('sale-list'), self._sale_body('cash'),
                              format='json', HTTP_IDEMPOTENCY_KEY='shared-key')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.content)

        # Tenant B needs routing under GA-2 before it can sell at all.
        _grant_default_routing(self.tenant_b, self.branch_b)
        self.client.force_authenticate(user=self.cashier_b)
        body_b = {
            'items': [{'product': self.product_b.id, 'qty': '2', 'price_each': '10.00'}],
            'method': 'cash', 'amount_paid': '20.00',
        }
        r2 = self.client.post(reverse('sale-list'), body_b, format='json',
                              HTTP_IDEMPOTENCY_KEY='shared-key')
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.content)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(Sale.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Sale.objects.filter(tenant=self.tenant_b).count(), 1)


class ProvisionDefaultPaymentRoutingCommandTests(APITestCase):
    """Step-4 provisioning command (the R-F replacement for the rejected 0017
    backfill migration): dry-run by default, --apply commits, reuse / skip /
    demote semantics, and strict --tenant scoping."""

    def _run(self, *args):
        out = StringIO()
        call_command('provision_default_payment_routing', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_is_default_and_writes_nothing(self):
        tenant = Tenant.objects.create(name='Legacy Tenant')
        branch = Branch.objects.create(tenant=tenant, name='Legacy Branch')

        output = self._run()

        self.assertIn('DRY-RUN', output)
        self.assertIn('CREATE route', output)   # the plan is printed…
        self.assertIn('Rolled back', output)
        # …but nothing is persisted.
        self.assertEqual(BranchPaymentMethod.objects.filter(branch=branch).count(), 0)
        self.assertEqual(FinancialAccount.objects.filter(tenant=tenant).count(), 0)
        self.assertEqual(PaymentMethod.objects.filter(tenant=tenant).count(), 0)

    def test_apply_provisions_default_routing_and_is_idempotent(self):
        tenant = Tenant.objects.create(name='Legacy Tenant')
        branch = Branch.objects.create(tenant=tenant, name='Legacy Branch')

        self._run('--apply')

        rows = BranchPaymentMethod.objects.filter(branch=branch).select_related(
            'payment_method', 'destination_account')
        self.assertEqual(rows.count(), 3)
        wiring = {
            r.payment_method.method_type: r.destination_account.account_type
            for r in rows
        }
        self.assertEqual(wiring, {
            'cash': 'cashbox', 'card': 'card_settlement', 'wallet': 'wallet',
        })
        self.assertTrue(all(r.is_default and r.is_active for r in rows))
        # Every created row stays inside the branch's own tenant.
        self.assertTrue(all(r.tenant_id == tenant.id for r in rows))
        self.assertTrue(all(
            r.destination_account.tenant_id == tenant.id for r in rows))

        # Second apply: idempotent — no duplicates, branch reported as skipped.
        output = self._run('--apply')
        self.assertEqual(BranchPaymentMethod.objects.filter(branch=branch).count(), 3)
        self.assertIn('SKIP', output)

    def test_apply_reuses_existing_accounts_and_methods(self):
        tenant = Tenant.objects.create(name='Partially Setup Tenant')
        branch = Branch.objects.create(tenant=tenant, name='B')
        existing_cashbox = FinancialAccount.objects.create(
            tenant=tenant, name='My Cashbox',
            account_type=FinancialAccount.AccountType.CASHBOX)
        existing_cash_pm = PaymentMethod.objects.create(
            tenant=tenant, name='My Cash', method_type='cash')

        output = self._run('--apply')

        cash_route = BranchPaymentMethod.objects.get(
            branch=branch, payment_method__method_type='cash')
        self.assertEqual(cash_route.destination_account_id, existing_cashbox.id)
        self.assertEqual(cash_route.payment_method_id, existing_cash_pm.id)
        self.assertIn('REUSE account', output)
        self.assertIn('REUSE payment method', output)

    def test_apply_skips_configured_branch(self):
        tenant = Tenant.objects.create(name='Configured Tenant')
        branch = Branch.objects.create(tenant=tenant, name='C')
        acct = FinancialAccount.objects.create(
            tenant=tenant, name='CB',
            account_type=FinancialAccount.AccountType.CASHBOX)
        pm = PaymentMethod.objects.create(
            tenant=tenant, name='Cash', method_type='cash')
        BranchPaymentMethod.objects.create(
            tenant=tenant, branch=branch, payment_method=pm,
            destination_account=acct, is_default=True, is_active=True)

        output = self._run('--apply')

        # Untouched: still exactly the one pre-existing route.
        self.assertEqual(BranchPaymentMethod.objects.filter(branch=branch).count(), 1)
        self.assertIn('SKIP', output)
        # The partially-configured branch is flagged for the operator (card +
        # wallet have no active route → those sales will 400 under GA-2).
        self.assertIn('WARN', output)

    def test_apply_demotes_duplicate_defaults_keeping_newest(self):
        tenant = Tenant.objects.create(name='Dup Tenant')
        branch = Branch.objects.create(tenant=tenant, name='D')
        acct = FinancialAccount.objects.create(
            tenant=tenant, name='CB',
            account_type=FinancialAccount.AccountType.CASHBOX)
        pm1 = PaymentMethod.objects.create(tenant=tenant, name='Cash 1', method_type='cash')
        pm2 = PaymentMethod.objects.create(tenant=tenant, name='Cash 2', method_type='cash')
        older = BranchPaymentMethod.objects.create(
            tenant=tenant, branch=branch, payment_method=pm1,
            destination_account=acct, is_default=True, is_active=True)
        newer = BranchPaymentMethod.objects.create(
            tenant=tenant, branch=branch, payment_method=pm2,
            destination_account=acct, is_default=True, is_active=True)

        output = self._run('--apply')

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertFalse(older.is_default)
        self.assertTrue(newer.is_default)
        self.assertIn('DEMOTE', output)

    def test_tenant_flag_scopes_both_passes_to_that_tenant_only(self):
        tenant_a = Tenant.objects.create(name='Scoped A')
        branch_a = Branch.objects.create(tenant=tenant_a, name='A')
        tenant_b = Tenant.objects.create(name='Scoped B')
        branch_b = Branch.objects.create(tenant=tenant_b, name='B')
        # Duplicate defaults in tenant B must survive a tenant-A-scoped run.
        acct_b = FinancialAccount.objects.create(
            tenant=tenant_b, name='CB-B',
            account_type=FinancialAccount.AccountType.CASHBOX)
        pm_b1 = PaymentMethod.objects.create(tenant=tenant_b, name='C1', method_type='cash')
        pm_b2 = PaymentMethod.objects.create(tenant=tenant_b, name='C2', method_type='cash')
        dup_1 = BranchPaymentMethod.objects.create(
            tenant=tenant_b, branch=branch_b, payment_method=pm_b1,
            destination_account=acct_b, is_default=True, is_active=True)
        dup_2 = BranchPaymentMethod.objects.create(
            tenant=tenant_b, branch=branch_b, payment_method=pm_b2,
            destination_account=acct_b, is_default=True, is_active=True)

        self._run('--apply', f'--tenant={tenant_a.id}')

        # Tenant A provisioned; tenant B completely untouched.
        self.assertEqual(BranchPaymentMethod.objects.filter(branch=branch_a).count(), 3)
        dup_1.refresh_from_db()
        dup_2.refresh_from_db()
        self.assertTrue(dup_1.is_default)
        self.assertTrue(dup_2.is_default)
        self.assertEqual(
            FinancialAccount.objects.filter(tenant=tenant_b).count(), 1)
        self.assertEqual(
            PaymentMethod.objects.filter(tenant=tenant_b).count(), 2)
        # Nothing created for tenant A leaked into tenant B's scope.
        self.assertEqual(
            BranchPaymentMethod.objects.filter(tenant=tenant_a).count(), 3)

    def test_unknown_tenant_raises_command_error(self):
        with self.assertRaises(CommandError):
            self._run('--apply', '--tenant=999999')
