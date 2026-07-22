"""Backfill per-branch `InventoryCost` rows from the tenant-wide average
(Sprint 5 Batch 1 — D-09 reopened to branch-wide costing).

Not required for correctness: `pos.services.costing.get_or_create_inventory_cost`
already lazily seeds a branch's `InventoryCost` row from the tenant-wide
(`branch=None`) row the first time that branch transacts. This command
exists for the same reason `seed_inventory_costs` did in Sprint 3 — an
operator can run it right after upgrading so every active branch has a
*visible* opening average immediately (useful for a "cost by branch" report
before that branch's first post-upgrade purchase), instead of relying on a
side effect of the first write.

Sprint 2 Batch 4 (directive R-F): master-data rows are never created inside
`migrate`. An operator runs this command, reviews the dry-run report, and
re-runs with `--apply` to commit — the exact pattern of `seed_product_units`
/ `seed_inventory_costs`.

What it does, per tenant (all tenants by default, or one via `--tenant`):
  for every product that already has a tenant-wide (`branch=None`)
  `InventoryCost` row, and every active branch, create a `(product, branch)`
  row seeded from the tenant-wide row's `avg_unit_cost` — unless that
  `(product, branch)` row already exists (never overwritten).

Idempotent by construction: the write is `get_or_create` keyed on the
`(product, branch)` unique constraint; a second `--apply` run finds
everything present and changes nothing. Dry-run executes the same code
inside a transaction and rolls it back, so the printed plan is exactly what
`--apply` would do.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Branch, Tenant
from pos.models import InventoryCost, Product


class _DryRunRollback(Exception):
    """Raised after a dry-run pass to abort the wrapping transaction."""


class Command(BaseCommand):
    help = (
        'Backfill per-branch InventoryCost rows, seeded from each product\'s '
        'tenant-wide average. Dry-run by default; pass --apply to commit '
        '(optionally scoped with --tenant=<id>). Never overwrites an '
        'existing (product, branch) InventoryCost row.'
    )

    def _say(self, msg, style=None):
        """Console-safe write (tenant/product/branch names are routinely
        Arabic; legacy Windows codepages can't encode them — degrade, don't
        crash)."""
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
        self.stdout.write(f'[{mode}] backfill_branch_inventory_cost - {scope}')
        if not apply_changes:
            self.stdout.write(
                '[DRY-RUN] No changes will be committed. Re-run with --apply '
                'to write the plan below.'
            )

        self._stats = defaultdict(int)

        try:
            with transaction.atomic():
                for tenant in tenants.iterator():
                    self._backfill_tenant(tenant)
                if not apply_changes:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass

        s = self._stats
        self.stdout.write(
            f'[{mode}] Summary: '
            f'{s["created"]} branch InventoryCost row(s) created, '
            f'{s["existing"]} already present, '
            f'{s["skipped_no_base"]} product(s) skipped (no tenant-wide row yet).'
        )
        if not apply_changes:
            self.stdout.write('[DRY-RUN] Rolled back - the database was not modified.')

    def _backfill_tenant(self, tenant):
        branches = list(Branch.objects.filter(tenant=tenant, active=True).order_by('id'))
        if not branches:
            return
        self._say(f'Tenant id={tenant.id} "{tenant.name}" — {len(branches)} active branch(es)')

        products = Product.objects.filter(tenant=tenant).order_by('id')
        for product in products.iterator():
            base = InventoryCost.objects.filter(product=product, branch=None).first()
            if base is None:
                # No tenant-wide opening row yet — run seed_inventory_costs
                # first; nothing to seed a branch row FROM for this product.
                self._stats['skipped_no_base'] += 1
                continue

            for branch in branches:
                _, created = InventoryCost.objects.get_or_create(
                    product=product, branch=branch,
                    defaults={'tenant': tenant, 'avg_unit_cost': base.avg_unit_cost},
                )
                if created:
                    self._stats['created'] += 1
                    self._say(
                        f'  CREATE InventoryCost product={product.id} '
                        f'"{product.name}" branch={branch.id} "{branch.name}" '
                        f'avg_unit_cost={base.avg_unit_cost} '
                        f'(opening value from tenant-wide average)'
                    )
                else:
                    self._stats['existing'] += 1
