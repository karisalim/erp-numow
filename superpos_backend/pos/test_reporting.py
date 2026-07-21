"""Sprint 4 — Advanced Reporting & Analytics.

Batch 1: `GET /api/dashboard/trend/` — one row per day across a window
(the raw series backing the Margin/COGS chart). Batch 2: optional
`?branch_id=` scoping on `dashboard_summary`/`dashboard_top_products`/
`dashboard_trend`, plus the `top_products` product-id fix (grouping by
`product` FK instead of only the free-text `product_name` snapshot) so the
frontend has something to drill down into. Batch 3: `?start_date=&
end_date=&source_document_type=` filtering on `GET
/products/{pk}/cost-movements/`, mirroring `StockMovementFilter`'s shape.
Batch 4: `GET /products/{pk}/cost-movements/export/?export_format=csv|xlsx|pdf`
— the same audit trail as a downloadable file. (Named `export_format`, not
`format` — the latter is reserved by DRF's content negotiation.)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Branch, Tenant, User
from pos.models import (
    Category, InventoryCost, InventoryCostMovement, Product, Sale, SaleItem,
)


class _Sprint4ReportingTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name='S4 Reporting Tenant')
        cls.branch_a = Branch.objects.create(tenant=cls.tenant, name='Branch A')
        cls.branch_b = Branch.objects.create(tenant=cls.tenant, name='Branch B')
        cls.manager = User.objects.create_user(
            username='s4mgr', password='pw', role=User.Role.MANAGER, tenant=cls.tenant,
        )
        cls.cashier = User.objects.create_user(
            username='s4cash', password='pw', role=User.Role.CASHIER, tenant=cls.tenant,
        )
        cls.category = Category.objects.create(tenant=cls.tenant, name='Grocery')
        cls.coffee = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Coffee', barcode='S4-1', sku='SKU-S4-1',
            price=Decimal('700.00'), cost=Decimal('500.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.coffee, avg_unit_cost=Decimal('500.0000'),
        )
        cls.tea = Product.objects.create(
            tenant=cls.tenant, category=cls.category,
            name='Tea', barcode='S4-2', sku='SKU-S4-2',
            price=Decimal('200.00'), cost=Decimal('80.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('100'),
        )
        InventoryCost.objects.create(
            tenant=cls.tenant, product=cls.tea, avg_unit_cost=Decimal('80.0000'),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _make_sale(self, items, *, branch=None, tax_amount=Decimal('0'),
                    sale_status=Sale.Status.COMPLETED, on_date=None):
        """`items`: list of (product, qty, price_each, unit_cost) tuples.
        `on_date`: if given, back-dates `created_at` via a bulk .update()
        (Sale.created_at is auto_now_add, so it can't be set at .create()
        time — the same pattern any Django test needing a specific date
        must use)."""
        subtotal = sum((qty * price_each for _, qty, price_each, _ in items), Decimal('0'))
        total = subtotal + tax_amount
        sale = Sale.objects.create(
            tenant=self.tenant, branch=branch or self.branch_a, cashier=self.manager,
            subtotal=subtotal, tax_amount=tax_amount, total=total,
            method=Sale.Method.CASH, paid=total, change=Decimal('0'), status=sale_status,
        )
        for product, qty, price_each, unit_cost in items:
            SaleItem.objects.create(
                sale=sale, product=product, product_name=product.name,
                barcode=product.barcode or '', qty=qty, price_each=price_each,
                line_total=qty * price_each, unit_cost=unit_cost,
            )
        if on_date:
            Sale.objects.filter(pk=sale.pk).update(
                created_at=timezone_aware(on_date),
            )
            sale.refresh_from_db()
        return sale


def timezone_aware(d):
    from django.utils import timezone
    import datetime
    return timezone.make_aware(datetime.datetime.combine(d, datetime.time(12, 0)))


class DashboardTrendTests(_Sprint4ReportingTestBase):
    def test_per_day_series_across_three_days(self):
        today = date.today()
        d1, d2, d3 = today - timedelta(days=2), today - timedelta(days=1), today

        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
            on_date=d1,
        )
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            on_date=d2,
        )
        # d3: no sales — must appear as a zero row, not a gap.

        resp = self.client.get(reverse('dashboard-trend'), {
            'start_date': d1.isoformat(), 'end_date': d3.isoformat(),
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        days = {row['date']: row for row in resp.json()['days']}

        self.assertEqual(len(days), 3)
        self.assertEqual(days[d1.isoformat()]['net_revenue'], 7000.0)
        self.assertEqual(days[d1.isoformat()]['cogs'], 5000.0)
        self.assertEqual(days[d1.isoformat()]['gross_profit'], 2000.0)

        self.assertEqual(days[d2.isoformat()]['net_revenue'], 1000.0)
        self.assertEqual(days[d2.isoformat()]['cogs'], 400.0)
        self.assertEqual(days[d2.isoformat()]['gross_profit'], 600.0)

        self.assertEqual(days[d3.isoformat()]['net_revenue'], 0.0)
        self.assertEqual(days[d3.isoformat()]['cogs'], 0.0)
        self.assertEqual(days[d3.isoformat()]['gross_profit'], 0.0)
        self.assertEqual(days[d3.isoformat()]['gross_margin_pct'], 0.0)

    def test_voided_sale_excluded(self):
        today = date.today()
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            on_date=today, sale_status=Sale.Status.VOIDED,
        )
        resp = self.client.get(reverse('dashboard-trend'), {
            'start_date': today.isoformat(), 'end_date': today.isoformat(),
        })
        day = resp.json()['days'][0]
        self.assertEqual(day['net_revenue'], 0.0)
        self.assertEqual(day['cogs'], 0.0)

    def test_cashier_forbidden(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.get(reverse('dashboard-trend'))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_date_returns_400(self):
        resp = self.client.get(reverse('dashboard-trend'), {'start_date': 'not-a-date'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class DashboardBranchFilterTests(_Sprint4ReportingTestBase):
    def test_dashboard_summary_branch_filter_narrows_to_one_branch(self):
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
            branch=self.branch_a,
        )
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            branch=self.branch_b,
        )

        resp = self.client.get(reverse('dashboard-summary'), {'branch_id': self.branch_a.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        kpis = resp.json()['kpis']
        self.assertEqual(kpis['net_revenue'], 7000.0)
        self.assertEqual(kpis['cogs'], 5000.0)
        names = {row['name'] for row in resp.json()['top_products']}
        self.assertEqual(names, {'Coffee'})

    def test_no_branch_id_is_unfiltered_regression(self):
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
            branch=self.branch_a,
        )
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            branch=self.branch_b,
        )
        resp = self.client.get(reverse('dashboard-summary'))
        kpis = resp.json()['kpis']
        self.assertEqual(kpis['net_revenue'], 8000.0)
        self.assertEqual(kpis['cogs'], 5400.0)

    def test_invalid_branch_id_returns_400(self):
        resp = self.client.get(reverse('dashboard-summary'), {'branch_id': 'nope'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_branch_id_returns_404(self):
        resp = self.client.get(reverse('dashboard-summary'), {'branch_id': 999999})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_tenant_branch_id_returns_404(self):
        other_tenant = Tenant.objects.create(name='S4 Other Tenant')
        other_branch = Branch.objects.create(tenant=other_tenant, name='Other Branch')
        resp = self.client.get(reverse('dashboard-summary'), {'branch_id': other_branch.pk})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_dashboard_trend_branch_filter(self):
        today = date.today()
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
            branch=self.branch_a, on_date=today,
        )
        self._make_sale(
            [(self.tea, Decimal('5'), Decimal('200.00'), Decimal('80.00'))],
            branch=self.branch_b, on_date=today,
        )
        resp = self.client.get(reverse('dashboard-trend'), {
            'start_date': today.isoformat(), 'end_date': today.isoformat(),
            'branch_id': self.branch_a.pk,
        })
        day = resp.json()['days'][0]
        self.assertEqual(day['net_revenue'], 7000.0)
        self.assertEqual(day['cogs'], 5000.0)


class TopProductsProductIdTests(_Sprint4ReportingTestBase):
    def test_dashboard_summary_top_products_includes_product_id(self):
        self._make_sale([(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))])
        resp = self.client.get(reverse('dashboard-summary'))
        row = resp.json()['top_products'][0]
        self.assertEqual(row['id'], self.coffee.pk)
        self.assertEqual(row['name'], 'Coffee')

    def test_standalone_top_products_endpoint_includes_product_id(self):
        today = date.today()
        self._make_sale(
            [(self.coffee, Decimal('10'), Decimal('700.00'), Decimal('500.00'))],
            on_date=today,
        )
        resp = self.client.get(reverse('dashboard-top-products'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        row = resp.json()[0]
        self.assertEqual(row['id'], self.coffee.pk)
        self.assertNotIn('product', row, 'internal grouping key should be renamed to id, not duplicated')

    def test_deleted_product_excluded_not_crashed(self):
        """SaleItem.product is SET_NULL — a sale item whose product was
        later deleted must be excluded from the ranking (no id to drill
        into), not crash or appear with id=None."""
        throwaway = Product.objects.create(
            tenant=self.tenant, category=self.category,
            name='Throwaway', barcode='S4-3', sku='SKU-S4-3',
            price=Decimal('50.00'), cost=Decimal('20.00'),
            tax_rate=Decimal('0.00'), stock=Decimal('10'),
        )
        self._make_sale([
            (self.coffee,   Decimal('10'), Decimal('700.00'), Decimal('500.00')),
            (throwaway,     Decimal('1'),  Decimal('50.00'),  Decimal('20.00')),
        ])
        throwaway.delete()

        resp = self.client.get(reverse('dashboard-summary'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        names = {row['name'] for row in resp.json()['top_products']}
        self.assertEqual(names, {'Coffee'})


class CostMovementDateFilterTests(_Sprint4ReportingTestBase):
    """Sprint 4 Batch 3 — `?start_date=&end_date=&source_document_type=` on
    `GET /products/{pk}/cost-movements/`. `occurred_at` is auto_now_add,
    so movements are back-dated via a bulk `.update()` after creation, same
    technique `_make_sale`'s `on_date` uses for `Sale.created_at`."""

    def _make_movement(self, *, on_date, source_document_type='purchase_invoice',
                        avg_before=Decimal('500.0000'), avg_after=Decimal('550.0000')):
        inv_cost, _ = InventoryCost.objects.get_or_create(
            tenant=self.tenant, product=self.coffee,
            defaults={'avg_unit_cost': avg_after},
        )
        m = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=inv_cost,
            quantity_before=Decimal('10'), quantity_received=Decimal('10'),
            unit_cost_received=Decimal('600.00'),
            avg_cost_before=avg_before, avg_cost_after=avg_after,
            source_document_type=source_document_type, source_document_id=1,
        )
        InventoryCostMovement.objects.filter(pk=m.pk).update(
            occurred_at=timezone_aware(on_date),
        )
        m.refresh_from_db()
        return m

    def test_date_range_narrows_results(self):
        today = date.today()
        old, recent = today - timedelta(days=60), today - timedelta(days=1)
        self._make_movement(on_date=old)
        self._make_movement(on_date=recent)

        resp = self.client.get(
            reverse('product-cost-movements', args=[self.coffee.id]),
            {'start_date': (today - timedelta(days=7)).isoformat(), 'end_date': today.isoformat()},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertEqual(resp.json()['count'], 1)

    def test_source_document_type_filter(self):
        self._make_movement(on_date=date.today(), source_document_type='purchase_invoice')
        self._make_movement(on_date=date.today(), source_document_type='manual_cost_adjustment')

        resp = self.client.get(
            reverse('product-cost-movements', args=[self.coffee.id]),
            {'source_document_type': 'manual_cost_adjustment'},
        )
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['source_document_type'], 'manual_cost_adjustment')

    def test_no_filter_params_is_unfiltered_regression(self):
        self._make_movement(on_date=date.today() - timedelta(days=400))
        self._make_movement(on_date=date.today())
        resp = self.client.get(reverse('product-cost-movements', args=[self.coffee.id]))
        self.assertEqual(resp.json()['count'], 2)

    def test_combined_with_pagination(self):
        for i in range(3):
            self._make_movement(on_date=date.today())
        resp = self.client.get(
            reverse('product-cost-movements', args=[self.coffee.id]),
            {'start_date': date.today().isoformat(), 'page_size': 2},
        )
        self.assertEqual(resp.json()['count'], 3)
        self.assertEqual(len(resp.json()['results']), 2)


class CostHistoryExportTests(_Sprint4ReportingTestBase):
    """Sprint 4 Batch 4 — CSV/Excel/PDF export of the AVCO audit trail."""

    def _make_movement(self, *, on_date=None):
        inv_cost, _ = InventoryCost.objects.get_or_create(
            tenant=self.tenant, product=self.coffee,
            defaults={'avg_unit_cost': Decimal('550.0000')},
        )
        m = InventoryCostMovement.objects.create(
            tenant=self.tenant, product=self.coffee, inventory_cost=inv_cost,
            quantity_before=Decimal('10'), quantity_received=Decimal('10'),
            unit_cost_received=Decimal('600.00'),
            avg_cost_before=Decimal('500.0000'), avg_cost_after=Decimal('550.0000'),
            source_document_type='purchase_invoice', source_document_id=7,
            note='test movement',
        )
        if on_date:
            InventoryCostMovement.objects.filter(pk=m.pk).update(
                occurred_at=timezone_aware(on_date),
            )
        return m

    def test_csv_export_200_correct_headers_and_content(self):
        self._make_movement()
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'csv'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('attachment; filename=', resp['Content-Disposition'])
        body = resp.content.decode('utf-8-sig')
        self.assertIn('Date,Source,Qty received', body)
        self.assertIn('purchase_invoice #7', body)
        self.assertIn('550.0000', body)

    def test_xlsx_export_200_correct_content_type_and_rows(self):
        self._make_movement()
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'xlsx'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('spreadsheetml.sheet', resp['Content-Type'])
        self.assertIn('attachment; filename=', resp['Content-Disposition'])

        from io import BytesIO
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(resp.content))
        ws = wb.active
        self.assertEqual(ws['A1'].value, 'Date')
        self.assertEqual(ws.max_row, 2, 'header row + 1 data row')

    def test_pdf_export_200_correct_content_type(self):
        self._make_movement()
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'pdf'},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename=', resp['Content-Disposition'])
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_empty_result_still_returns_valid_file_not_500(self):
        for fmt, expected_ct in (
            ('csv', 'text/csv'), ('xlsx', 'spreadsheetml.sheet'), ('pdf', 'application/pdf'),
        ):
            resp = self.client.get(
                reverse('product-cost-movements-export', args=[self.coffee.id]),
                {'export_format': fmt},
            )
            self.assertEqual(resp.status_code, status.HTTP_200_OK, f'{fmt} export crashed on empty data')
            self.assertIn(expected_ct, resp['Content-Type'])

    def test_date_range_narrows_export(self):
        old, recent = date.today() - timedelta(days=60), date.today()
        self._make_movement(on_date=old)
        self._make_movement(on_date=recent)
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'csv', 'start_date': (date.today() - timedelta(days=7)).isoformat(),
             'end_date': date.today().isoformat()},
        )
        body = resp.content.decode('utf-8-sig')
        # Header + exactly 1 data row.
        self.assertEqual(len(body.strip().splitlines()), 2)

    def test_invalid_format_returns_400(self):
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'txt'},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cashier_forbidden(self):
        self.client.force_authenticate(user=self.cashier)
        resp = self.client.get(
            reverse('product-cost-movements-export', args=[self.coffee.id]),
            {'export_format': 'csv'},
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
