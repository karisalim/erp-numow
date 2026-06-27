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
from pos.models import Category, Payment, Product, Sale
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
