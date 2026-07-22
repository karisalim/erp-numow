"""Backfill `InventoryCost` rows from the existing `Product.cost` mirror
(Sprint 3 Batch 1).

Sprint 2 Batch 4 (directive R-F): master-data rows are never created inside
`migrate`. An operator runs this command, reviews the dry-run report, and
re-runs with `--apply` to commit — the exact pattern of
`seed_product_units` / `provision_default_payment_routing`.

What it does, per tenant (all tenants by default, or one via `--tenant`):
  every product without an `InventoryCost` row gets one, seeded from its
  current `Product.cost` (the opening average). No `InventoryCostMovement`
  row is written — an opening value is not a "movement" (same convention
  D-17 already uses for FinancialAccount/Customer/Supplier opening
  balances: stored, never posted).

Products that already have an `InventoryCost` row (e.g. re-running after a
partial apply) are left untouched — this command never overwrites an
existing average.

Idempotent by construction: the write is `get_or_create` keyed on the
`product` OneToOneField's implied uniqueness; a second `--apply` run finds
everything present and changes nothing. Dry-run executes the same code
inside a transaction and rolls it back, so the printed plan is exactly what
`--apply` would do.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Tenant
from pos.models import InventoryCost, Product


class _DryRunRollback(Exception):
    """Raised after a dry-run pass to abort the wrapping transaction."""


class Command(BaseCommand):
    help = (
        'Backfill InventoryCost rows from Product.cost. Dry-run by default; '
        'pass --apply to commit (optionally scoped with --tenant=<id>). '
        'Never overwrites an existing InventoryCost row.'
    )

    def _say(self, msg, style=None):
        """Console-safe write (tenant/product names are routinely Arabic;
        legacy Windows codepages can't encode them — degrade, don't crash)."""
        if style is not None:
            msg = style(msg)
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            safe = msg.encode('ascii', errors='backslashreplace').decode('ascii')
            self.stdout.write(safe)

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Commit the changes. Without this flag the command runs the '
                 'full pass in a transaction and rolls it back (dry-run).',
        )
        parser.add_argument(
            '--tenant', type=int, default=None, metavar='ID',
            help='Limit the run to one tenant id.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        tenant_id = options['tenant']

        tenants = Tenant.objects.order_by('id')
        if tenant_id is not None:
            tenants = tenants.filter(pk=tenant_id)
            if not tenants.exists():
                raise CommandError(f'Tenant id={tenant_id} does not exist.')

        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        scope = f'tenant={tenant_id}' if tenant_id is not None else 'all tenants'
        self.stdout.write(f'[{mode}] seed_inventory_costs - {scope}')
        if not apply_changes:
            self.stdout.write(
                '[DRY-RUN] No changes will be committed. Re-run with --apply '
                'to write the plan below.'
            )

        self._stats = defaultdict(int)

        try:
            with transaction.atomic():
                for tenant in tenants.iterator():
                    self._seed_tenant(tenant)
                if not apply_changes:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass

        s = self._stats
        self.stdout.write(
            f'[{mode}] Summary: '
            f'{s["created"]} InventoryCost row(s) created, '
            f'{s["existing"]} already present.'
        )
        if not apply_changes:
            self.stdout.write('[DRY-RUN] Rolled back - the database was not modified.')

    def _seed_tenant(self, tenant):
        self._say(f'Tenant id={tenant.id} "{tenant.name}"')
        # Sprint 5 Batch 1: InventoryCost.product is now a plain FK (a
        # product can have several rows, one per branch), so the reverse
        # relation is no longer select_related-able the way the old
        # OneToOneField was — this command only ever seeds the tenant-wide
        # (branch=None) opening row, so no prefetch is needed for its shape.
        products = Product.objects.filter(tenant=tenant).order_by('id')
        for product in products.iterator():
            _, created = InventoryCost.objects.get_or_create(
                product=product, branch=None,
                defaults={'tenant': tenant, 'avg_unit_cost': product.cost},
            )
            if created:
                self._stats['created'] += 1
                self._say(
                    f'  CREATE InventoryCost product={product.id} '
                    f'"{product.name}" avg_unit_cost={product.cost} '
                    f'(opening value from Product.cost)'
                )
            else:
                self._stats['existing'] += 1
