"""Gate A migration safety — backfill payment routing for legacy branches.

Strict payment routing (Release Gate A) removes the legacy behavior where a
branch with zero BranchPaymentMethod rows could complete a sale while GL
posting was silently skipped. To guarantee no existing branch stops selling
on deploy, this data migration provisions the default setup for every branch
that has no routing at all:

    * one tenant-level FinancialAccount per needed type
      (cashbox / card_settlement / wallet) — reusing the first existing
      active account of that type when the tenant already has one;
    * one tenant-level PaymentMethod per method type (cash / card / wallet) —
      reusing the first existing one of that type when present;
    * an active, default BranchPaymentMethod wiring each method to its
      matching account.

It also repairs pre-existing default duplicates: when a branch has more than
one ACTIVE default route for the same method_type (now rejected by the
serializer), the newest row (highest id) keeps `is_default=True` and the rest
are demoted.

Idempotent by construction: branches that already have any BranchPaymentMethod
rows are skipped by the backfill, and the de-dup pass only demotes rows while
a duplicate exists. Purely additive — no schema changes, no deletions.
"""

from collections import defaultdict

from django.db import migrations


# Kept as plain strings (not model enums) so the migration is stable even if
# the TextChoices classes move or gain members later.
_METHOD_TO_ACCOUNT_TYPE = {
    'cash':   'cashbox',
    'card':   'card_settlement',
    'wallet': 'wallet',
}

_DEFAULT_ACCOUNT_NAMES = {
    'cashbox':         'Main Cashbox',
    'card_settlement': 'Card Settlement',
    'wallet':          'Wallet',
}

_DEFAULT_METHOD_NAMES = {
    'cash':   'Cash',
    'card':   'Card',
    'wallet':  'Wallet',
}


def _ensure_account(FinancialAccount, tenant, account_type):
    """First active account of this type for the tenant, or a new default one."""
    acct = (
        FinancialAccount.objects
        .filter(tenant=tenant, account_type=account_type, is_active=True)
        .order_by('id')
        .first()
    )
    if acct is not None:
        return acct
    return FinancialAccount.objects.create(
        tenant=tenant,
        name=_DEFAULT_ACCOUNT_NAMES[account_type],
        account_type=account_type,
    )


def _ensure_payment_method(PaymentMethod, tenant, method_type):
    """First active method of this type for the tenant, or a new default one."""
    pm = (
        PaymentMethod.objects
        .filter(tenant=tenant, method_type=method_type, is_active=True)
        .order_by('id')
        .first()
    )
    if pm is not None:
        return pm
    # (tenant, name) is unique — suffix defensively in case a differently-typed
    # method already took the plain name.
    name = _DEFAULT_METHOD_NAMES[method_type]
    if PaymentMethod.objects.filter(tenant=tenant, name=name).exists():
        name = f'{name} (default)'
    return PaymentMethod.objects.create(
        tenant=tenant, name=name, method_type=method_type,
    )


def backfill_routing(apps, schema_editor):
    Branch = apps.get_model('accounts', 'Branch')
    BranchPaymentMethod = apps.get_model('accounts', 'BranchPaymentMethod')
    FinancialAccount = apps.get_model('accounts', 'FinancialAccount')
    PaymentMethod = apps.get_model('accounts', 'PaymentMethod')

    for branch in Branch.objects.select_related('tenant').iterator():
        if BranchPaymentMethod.objects.filter(branch=branch).exists():
            continue  # already configured — leave untouched
        tenant = branch.tenant
        for method_type, account_type in _METHOD_TO_ACCOUNT_TYPE.items():
            acct = _ensure_account(FinancialAccount, tenant, account_type)
            pm = _ensure_payment_method(PaymentMethod, tenant, method_type)
            BranchPaymentMethod.objects.create(
                tenant=tenant, branch=branch,
                payment_method=pm, destination_account=acct,
                is_default=True, is_active=True,
            )


def demote_duplicate_defaults(apps, schema_editor):
    """Keep the newest active default per (branch, method_type); demote the rest."""
    BranchPaymentMethod = apps.get_model('accounts', 'BranchPaymentMethod')

    groups = defaultdict(list)
    rows = (
        BranchPaymentMethod.objects
        .filter(is_default=True, is_active=True)
        .select_related('payment_method')
        .order_by('branch_id', '-id')
    )
    for row in rows:
        groups[(row.branch_id, row.payment_method.method_type)].append(row)

    demote_ids = [
        row.id
        for dupes in groups.values() if len(dupes) > 1
        for row in dupes[1:]  # dupes[0] is the newest (ordered by -id)
    ]
    if demote_ids:
        BranchPaymentMethod.objects.filter(id__in=demote_ids).update(is_default=False)


def noop_reverse(apps, schema_editor):
    """Backfilled config is real tenant data once sales post against it —
    reversing would orphan movements, so the reverse is a deliberate no-op."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_add_balance_before'),
    ]

    operations = [
        migrations.RunPython(demote_duplicate_defaults, noop_reverse),
        migrations.RunPython(backfill_routing, noop_reverse),
    ]
