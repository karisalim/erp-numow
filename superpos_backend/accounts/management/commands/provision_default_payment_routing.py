"""Provision default payment routing for branches that have none.

Release Gate A replacement for the rejected data migration
`0017_backfill_branch_payment_routing` (directive R-F): financial rows are
never created inside `migrate`. Instead, an operator runs this command,
reviews the dry-run report, and re-runs with `--apply` to commit.

For every branch with ZERO `BranchPaymentMethod` rows it provisions the
default setup strict routing (GA-2) requires:

    * one tenant-level FinancialAccount per needed type
      (cashbox / card_settlement / wallet) — reusing the first existing
      active account of that type when the tenant already has one;
    * one tenant-level PaymentMethod per method type (cash / card / wallet) —
      reusing the first existing active one of that type when present;
    * an active, default BranchPaymentMethod wiring each method to its
      matching account.

It also repairs pre-existing default duplicates: when a branch has more than
one ACTIVE default route for the same method_type (now rejected by the
serializer), the newest row (highest id) keeps `is_default=True` and the rest
are demoted — the same tie-break the runtime resolver uses (`-is_default, -id`).

Branches that already have any routing are skipped untouched; for those the
command additionally reports (log-only) any of cash/card/wallet still missing
an active route, so the operator can close gaps before strict routing lands.

Idempotent by construction: a second `--apply` run finds every branch
configured and changes nothing. Dry-run executes the exact same code inside a
transaction and rolls it back, so the printed plan is what `--apply` would do.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import (
    Branch, BranchPaymentMethod, FinancialAccount, PaymentMethod, Tenant,
)


_METHOD_TO_ACCOUNT_TYPE = {
    PaymentMethod.MethodType.CASH:   FinancialAccount.AccountType.CASHBOX,
    PaymentMethod.MethodType.CARD:   FinancialAccount.AccountType.CARD_SETTLEMENT,
    PaymentMethod.MethodType.WALLET: FinancialAccount.AccountType.WALLET,
}

_DEFAULT_ACCOUNT_NAMES = {
    FinancialAccount.AccountType.CASHBOX:         'Main Cashbox',
    FinancialAccount.AccountType.CARD_SETTLEMENT: 'Card Settlement',
    FinancialAccount.AccountType.WALLET:          'Wallet',
}

_DEFAULT_METHOD_NAMES = {
    PaymentMethod.MethodType.CASH:   'Cash',
    PaymentMethod.MethodType.CARD:   'Card',
    PaymentMethod.MethodType.WALLET: 'Wallet',
}


class _DryRunRollback(Exception):
    """Raised after a dry-run pass to abort the wrapping transaction."""


class Command(BaseCommand):
    help = (
        'Provision default cash/card/wallet payment routing for branches '
        'that have no BranchPaymentMethod rows, and demote duplicate active '
        'default routes. Dry-run by default; pass --apply to commit '
        '(optionally scoped with --tenant=<id>).'
    )

    def _say(self, msg, style=None):
        """Console-safe write.

        Tenant/branch names are routinely Arabic; Windows consoles often run a
        legacy codepage (cp1252) that cannot encode them. Degrade unencodable
        characters to backslash escapes instead of crashing mid-run.
        """
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
            help='Limit the run to one tenant id (both demotion and backfill).',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        tenant_id = options['tenant']

        tenant = None
        if tenant_id is not None:
            try:
                tenant = Tenant.objects.get(pk=tenant_id)
            except Tenant.DoesNotExist:
                raise CommandError(f'Tenant id={tenant_id} does not exist.')

        mode = 'APPLY' if apply_changes else 'DRY-RUN'
        scope = f'tenant={tenant_id}' if tenant is not None else 'all tenants'
        self.stdout.write(f'[{mode}] provision_default_payment_routing - {scope}')
        if not apply_changes:
            self.stdout.write(
                '[DRY-RUN] No changes will be committed. Re-run with --apply '
                'to write the plan below.'
            )

        self._stats = defaultdict(int)

        try:
            with transaction.atomic():
                self._demote_duplicate_defaults(tenant)
                self._backfill_unrouted_branches(tenant)
                if not apply_changes:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass

        s = self._stats
        self.stdout.write(
            f'[{mode}] Summary: '
            f'{s["routes_created"]} route(s) created across '
            f'{s["branches_provisioned"]} branch(es); '
            f'{s["accounts_created"]} account(s) created, '
            f'{s["accounts_reused"]} reused; '
            f'{s["methods_created"]} payment method(s) created, '
            f'{s["methods_reused"]} reused; '
            f'{s["defaults_demoted"]} duplicate default(s) demoted; '
            f'{s["branches_skipped"]} already-configured branch(es) skipped.'
        )
        if not apply_changes:
            self.stdout.write('[DRY-RUN] Rolled back - the database was not modified.')

    # ── Pass 1: demote duplicate active defaults ─────────────────────────────

    def _demote_duplicate_defaults(self, tenant):
        """Keep the newest active default per (branch, method_type); demote the rest."""
        rows = (
            BranchPaymentMethod.objects
            .filter(is_default=True, is_active=True)
            .select_related('payment_method', 'branch')
            .order_by('branch_id', '-id')
        )
        if tenant is not None:
            rows = rows.filter(tenant=tenant)

        groups = defaultdict(list)
        for row in rows:
            groups[(row.branch_id, row.payment_method.method_type)].append(row)

        demote_ids = []
        for (branch_id, method_type), dupes in groups.items():
            if len(dupes) <= 1:
                continue
            keeper = dupes[0]  # newest (ordered by -id)
            for row in dupes[1:]:
                demote_ids.append(row.id)
                self._say(
                    f'  DEMOTE route id={row.id} '
                    f'(branch={branch_id} "{row.branch.name}", '
                    f'method_type={method_type}) - '
                    f'newest route id={keeper.id} keeps is_default=True'
                )
        if demote_ids:
            BranchPaymentMethod.objects.filter(id__in=demote_ids).update(is_default=False)
        self._stats['defaults_demoted'] = len(demote_ids)

    # ── Pass 2: backfill branches with zero routing ──────────────────────────

    def _backfill_unrouted_branches(self, tenant):
        branches = Branch.objects.select_related('tenant').order_by('tenant_id', 'id')
        if tenant is not None:
            branches = branches.filter(tenant=tenant)

        for branch in branches.iterator():
            if BranchPaymentMethod.objects.filter(branch=branch).exists():
                self._stats['branches_skipped'] += 1
                self._say(
                    f'  SKIP branch id={branch.id} "{branch.name}" '
                    f'(tenant={branch.tenant_id}) - already configured'
                )
                self._report_missing_routes(branch)
                continue

            self._stats['branches_provisioned'] += 1
            for method_type, account_type in _METHOD_TO_ACCOUNT_TYPE.items():
                acct = self._ensure_account(branch.tenant, account_type)
                pm = self._ensure_payment_method(branch.tenant, method_type)
                route = BranchPaymentMethod.objects.create(
                    tenant=branch.tenant, branch=branch,
                    payment_method=pm, destination_account=acct,
                    is_default=True, is_active=True,
                )
                self._stats['routes_created'] += 1
                self._say(
                    f'  CREATE route id={route.id} branch={branch.id} '
                    f'"{branch.name}" (tenant={branch.tenant_id}): '
                    f'{method_type} -> account id={acct.id} "{acct.name}" '
                    f'[{account_type}] (default, active)'
                )

    def _report_missing_routes(self, branch):
        """Log-only audit: a configured branch missing an active route for any
        of cash/card/wallet will 400 those sales under strict routing (GA-2)."""
        for method_type in _METHOD_TO_ACCOUNT_TYPE:
            has_active = BranchPaymentMethod.objects.filter(
                tenant=branch.tenant, branch=branch, is_active=True,
                payment_method__method_type=method_type,
            ).exists()
            if not has_active:
                self._say(
                    f'  WARN  branch id={branch.id} "{branch.name}" has no '
                    f'ACTIVE route for method_type={method_type} - sales with '
                    f'this method will be rejected under strict routing. '
                    f'Configure it manually (the command never alters '
                    f'partially-configured branches).',
                    style=self.style.WARNING,
                )

    # ── Reuse-or-create helpers ───────────────────────────────────────────────

    def _ensure_account(self, tenant, account_type):
        """First active account of this type for the tenant, or a new default one."""
        acct = (
            FinancialAccount.objects
            .filter(tenant=tenant, account_type=account_type, is_active=True)
            .order_by('id')
            .first()
        )
        if acct is not None:
            self._stats['accounts_reused'] += 1
            self._say(
                f'  REUSE account id={acct.id} "{acct.name}" '
                f'[{account_type}] (tenant={tenant.id})'
            )
            return acct
        acct = FinancialAccount.objects.create(
            tenant=tenant,
            name=_DEFAULT_ACCOUNT_NAMES[account_type],
            account_type=account_type,
        )
        self._stats['accounts_created'] += 1
        self._say(
            f'  CREATE account id={acct.id} "{acct.name}" '
            f'[{account_type}] (tenant={tenant.id})'
        )
        return acct

    def _ensure_payment_method(self, tenant, method_type):
        """First active method of this type for the tenant, or a new default one."""
        pm = (
            PaymentMethod.objects
            .filter(tenant=tenant, method_type=method_type, is_active=True)
            .order_by('id')
            .first()
        )
        if pm is not None:
            self._stats['methods_reused'] += 1
            self._say(
                f'  REUSE payment method id={pm.id} "{pm.name}" '
                f'[{method_type}] (tenant={tenant.id})'
            )
            return pm
        # (tenant, name) is unique — suffix defensively in case a
        # differently-typed method already took the plain name.
        name = _DEFAULT_METHOD_NAMES[method_type]
        if PaymentMethod.objects.filter(tenant=tenant, name=name).exists():
            name = f'{name} (default)'
        pm = PaymentMethod.objects.create(
            tenant=tenant, name=name, method_type=method_type,
        )
        self._stats['methods_created'] += 1
        self._say(
            f'  CREATE payment method id={pm.id} "{pm.name}" '
            f'[{method_type}] (tenant={tenant.id})'
        )
        return pm
