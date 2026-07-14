"""Seed ProductUnit mappings from the legacy `Product.unit` / `pack_qty`.

Sprint 2 Batch 4 (directive R-F): master-data rows are never created inside
`migrate`. An operator runs this command, reviews the dry-run report, and
re-runs with `--apply` to commit — the exact pattern of
`provision_default_payment_routing` (Sprint 1).

What it does, per tenant (all tenants by default, or one via `--tenant`):

  Pass 1 — unit substrate: get_or_create the unit groups/units needed to
      mirror the legacy enum (Count/Piece, Mass/Gram+Kilogram,
      Volume/Milliliter+Liter, Packaging/Carton). Existing rows are reused
      untouched — factors are NEVER edited (that would reinterpret data).

  Pass 2 — base mirror (1:1, no re-denomination): every product without a
      base ProductUnit gets one that mirrors its legacy `unit` enum exactly
      (kg stays kg — renaming the base would silently reinterpret the stock
      history denominated in it). conversion_to_base=1, is_base=True,
      is_sale_unit=True, is_purchase_unit=True.

  Pass 3 — pack mapping: products with `pack_qty > 1` (and a non-carton
      base) get ProductUnit(Carton, conversion=pack_qty, is_sale_unit=True),
      mirroring the legacy multi-pack semantics.

  Pass 4 — audit (log-only): legacy `Product.barcode` values that collide
      with a pack barcode in ProductBarcodeUnit are reported so the operator
      can resolve them before scan precedence lands (Batch 5).

Stock quantities are NEVER touched: the command writes only UnitGroup /
Unit / ProductUnit rows. Stock stays denominated in the (unchanged) base
unit, so no StockMovement / WarehouseStock / Product.stock value changes
meaning or magnitude.

Idempotent by construction: every write is get_or_create keyed on the DB
uniqueness constraints; a second `--apply` run finds everything present and
changes nothing. Dry-run executes the same code inside a transaction and
rolls it back, so the printed plan is exactly what `--apply` would do.
"""

from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Tenant
from pos.models import Product, ProductBarcodeUnit, ProductUnit, Unit, UnitGroup


#: Legacy `Product.unit` enum value → (group name, unit name, symbol,
#: factor_to_base, allow_decimal). Factors keep each seeded group internally
#: consistent (base = factor 1: Gram/Milliliter), but the per-product base
#: mapping always mirrors the legacy enum itself with conversion 1.
_LEGACY_UNIT_MAP = {
    Product.Unit.PIECE:  ('Count',     'Piece',      'pc',  Decimal('1'),    False),
    Product.Unit.KG:     ('Mass',      'Kilogram',   'kg',  Decimal('1000'), True),
    Product.Unit.LITER:  ('Volume',    'Liter',      'L',   Decimal('1000'), True),
    Product.Unit.CARTON: ('Packaging', 'Carton',     'ctn', Decimal('1'),    False),
}

#: Companion base units so seeded Mass/Volume groups keep the factor-1
#: convention the conversion service validates.
_GROUP_BASE_UNITS = {
    'Mass':   ('Gram',       'g',  Decimal('1'), True),
    'Volume': ('Milliliter', 'ml', Decimal('1'), True),
}


class _DryRunRollback(Exception):
    """Raised after a dry-run pass to abort the wrapping transaction."""


class Command(BaseCommand):
    help = (
        'Seed ProductUnit mappings from the legacy Product.unit enum and '
        'pack_qty. Dry-run by default; pass --apply to commit (optionally '
        'scoped with --tenant=<id>). Never modifies stock quantities.'
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
        self.stdout.write(f'[{mode}] seed_product_units - {scope}')
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
            f'{s["groups_created"]} unit group(s) created, '
            f'{s["units_created"]} unit(s) created, '
            f'{s["units_reused"]} reused; '
            f'{s["base_created"]} base mapping(s) created, '
            f'{s["base_existing"]} product(s) already had a base, '
            f'{s["base_conflict"]} skipped on conflict; '
            f'{s["packs_created"]} pack mapping(s) created, '
            f'{s["packs_existing"]} already present, '
            f'{s["packs_carton_base"]} skipped (carton base); '
            f'{s["barcode_collisions"]} barcode collision(s) reported.'
        )
        if not apply_changes:
            self.stdout.write('[DRY-RUN] Rolled back - the database was not modified.')

    # ── per-tenant run ────────────────────────────────────────────────────────

    def _seed_tenant(self, tenant):
        self._say(f'Tenant id={tenant.id} "{tenant.name}"')
        units = self._ensure_unit_substrate(tenant)
        self._mirror_legacy_bases(tenant, units)
        self._seed_pack_mappings(tenant, units)
        self._audit_barcode_collisions(tenant)

    # ── Pass 1: unit substrate ────────────────────────────────────────────────

    def _ensure_unit_substrate(self, tenant):
        """get_or_create the groups/units the legacy mirror needs.

        Returns {legacy enum value: Unit}. Existing rows are reused verbatim —
        factors are never modified.
        """
        groups = {}
        units_by_legacy = {}

        def ensure_group(name):
            if name not in groups:
                group, created = UnitGroup.objects.get_or_create(
                    tenant=tenant, name=name,
                )
                groups[name] = group
                if created:
                    self._stats['groups_created'] += 1
                    self._say(f'  CREATE unit group "{name}" (tenant={tenant.id})')
            return groups[name]

        def ensure_unit(group, name, symbol, factor, allow_decimal):
            unit, created = Unit.objects.get_or_create(
                tenant=tenant, unit_group=group, name=name,
                defaults={
                    'symbol': symbol,
                    'factor_to_base': factor,
                    'allow_decimal': allow_decimal,
                },
            )
            if created:
                self._stats['units_created'] += 1
                self._say(
                    f'  CREATE unit "{name}" ({symbol}) factor={factor} '
                    f'in group "{group.name}"'
                )
            else:
                self._stats['units_reused'] += 1
            return unit

        for legacy_value, (group_name, unit_name, symbol, factor,
                           allow_decimal) in _LEGACY_UNIT_MAP.items():
            group = ensure_group(group_name)
            # Keep the factor-1 convention: seed the group's base companion
            # (Gram / Milliliter) before its bigger sibling.
            if group_name in _GROUP_BASE_UNITS:
                base_name, base_symbol, base_factor, base_dec = \
                    _GROUP_BASE_UNITS[group_name]
                ensure_unit(group, base_name, base_symbol, base_factor, base_dec)
            units_by_legacy[legacy_value] = ensure_unit(
                group, unit_name, symbol, factor, allow_decimal,
            )
        return units_by_legacy

    # ── Pass 2: 1:1 base mirror ───────────────────────────────────────────────

    def _mirror_legacy_bases(self, tenant, units_by_legacy):
        products = (
            Product.objects.filter(tenant=tenant)
            .order_by('id')
        )
        for product in products.iterator():
            if ProductUnit.objects.filter(product=product, is_base=True).exists():
                self._stats['base_existing'] += 1
                continue

            unit = units_by_legacy.get(product.unit)
            if unit is None:
                # Unknown enum value (defensive — shouldn't happen).
                self._stats['base_conflict'] += 1
                self._say(
                    f'  WARN  product id={product.id} "{product.name}" has '
                    f'unmapped legacy unit {product.unit!r} - skipped',
                    style=self.style.WARNING,
                )
                continue

            # (tenant, product, unit) is unique: an existing NON-base mapping
            # for the mirror unit means someone configured this product by
            # hand in a way the mirror cannot reconcile - operator decision.
            if ProductUnit.objects.filter(product=product, unit=unit).exists():
                self._stats['base_conflict'] += 1
                self._say(
                    f'  WARN  product id={product.id} "{product.name}" already '
                    f'maps unit "{unit.name}" as a NON-base unit - base mirror '
                    f'skipped; resolve manually',
                    style=self.style.WARNING,
                )
                continue

            row = ProductUnit.objects.create(
                tenant=tenant, product=product, unit=unit,
                conversion_to_base=Decimal('1'), is_base=True,
                is_sale_unit=True, is_purchase_unit=True,
            )
            self._stats['base_created'] += 1
            self._say(
                f'  CREATE base mapping id={row.id} product={product.id} '
                f'"{product.name}" -> "{unit.name}" (mirror of legacy '
                f'{product.unit!r}, conversion=1)'
            )

    # ── Pass 3: pack mapping from pack_qty ────────────────────────────────────

    def _seed_pack_mappings(self, tenant, units_by_legacy):
        carton = units_by_legacy[Product.Unit.CARTON]
        products = (
            Product.objects.filter(tenant=tenant, pack_qty__gt=1)
            .order_by('id')
        )
        for product in products.iterator():
            if product.unit == Product.Unit.CARTON:
                # The base already IS the carton; pack_qty describes its
                # inner pieces, which is not expressible as a bigger unit.
                self._stats['packs_carton_base'] += 1
                self._say(
                    f'  SKIP  product id={product.id} "{product.name}" '
                    f'pack_qty={product.pack_qty} but base unit is carton - '
                    f'no pack mapping seeded'
                )
                continue
            if ProductUnit.objects.filter(product=product, unit=carton).exists():
                self._stats['packs_existing'] += 1
                continue
            row = ProductUnit.objects.create(
                tenant=tenant, product=product, unit=carton,
                conversion_to_base=product.pack_qty,
                is_base=False, is_sale_unit=True,
            )
            self._stats['packs_created'] += 1
            self._say(
                f'  CREATE pack mapping id={row.id} product={product.id} '
                f'"{product.name}" -> "Carton" x{product.pack_qty} '
                f'(from legacy pack_qty)'
            )

    # ── Pass 4: barcode collision audit (log-only) ────────────────────────────

    def _audit_barcode_collisions(self, tenant):
        """Report legacy Product.barcode values that also exist as pack
        barcodes — ambiguous once scan precedence lands (Batch 5). Log-only:
        this command never mutates barcodes."""
        pack_barcodes = set(
            ProductBarcodeUnit.objects.filter(tenant=tenant)
            .values_list('barcode', flat=True)
        )
        if not pack_barcodes:
            return
        collisions = (
            Product.objects
            .filter(tenant=tenant, barcode__in=pack_barcodes)
            .order_by('id')
        )
        for product in collisions.iterator():
            self._stats['barcode_collisions'] += 1
            self._say(
                f'  WARN  product id={product.id} "{product.name}" legacy '
                f'barcode "{product.barcode}" collides with a pack barcode '
                f'in ProductBarcodeUnit - resolve before scan precedence '
                f'ships (Batch 5)',
                style=self.style.WARNING,
            )
