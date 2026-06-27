import secrets

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Branch,
    BranchPaymentMethod,
    BranchSettings,
    BranchUserAssignment,
    Customer,
    FinancialAccount,
    FinancialAccountMovement,
    PaymentMethod,
    Supplier,
    Tenant,
)

User = get_user_model()


class BranchSerializer(serializers.ModelSerializer):
    """Legacy serializer kept for backward compatibility on
    /api/auth/branches/ and /api/accounts/branches/ mounts.

    The richer v3.6 surface lives in `BranchV2Serializer`; legacy clients
    keep seeing the same flat shape they expect.
    """

    class Meta:
        model  = Branch
        fields = ['id', 'name', 'address', 'phone', 'active', 'created_at']
        read_only_fields = ['id', 'created_at']


class BranchV2Serializer(serializers.ModelSerializer):
    """v3.6 master-data shape for the /api/branches/ surface.

    Adds `code`, `branch_type`, `tax_number`, `currency`, `timezone`,
    `is_main`, and exposes the legacy `active` column under the contract
    name `is_active` (MASTER_DATA_CONTRACT.md §4.3). `tenant` is read-only
    here — it is always set from the authenticated user, never accepted
    from the client.
    """

    is_active = serializers.BooleanField(source='active', required=False)

    class Meta:
        model  = Branch
        fields = [
            'id', 'tenant',
            'code', 'name', 'branch_type',
            'address', 'phone', 'tax_number',
            'currency', 'timezone',
            'is_main', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class BranchSettingsSerializer(serializers.ModelSerializer):
    """Settings document for a branch.

    Forward-declared `*_id` defaults (warehouses, cashbox, price tier) stay
    plain ints until those master tables exist in later slices.
    """

    class Meta:
        model  = BranchSettings
        fields = [
            'id', 'tenant', 'branch',
            'default_sales_warehouse_id',
            'default_purchase_warehouse_id',
            'default_cashbox_id',
            'default_main_safe_id',
            'default_price_tier_id',
            'require_shift_for_pos',
            'allow_negative_stock',
            'allow_shift_close_with_open_orders',
            'receipt_header',
            'receipt_footer',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'branch', 'created_at', 'updated_at']


class BranchUserAssignmentSerializer(serializers.ModelSerializer):
    """Maps a user to a branch with a per-branch role.

    `user` accepts a user id; the view sets `tenant` and `branch` from the
    URL/auth context — those are never trusted from the request body.
    """

    user_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model  = BranchUserAssignment
        fields = [
            'id', 'tenant', 'branch',
            'user', 'user_username',
            'role_at_branch', 'is_default_branch', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'branch', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    full_name             = serializers.SerializerMethodField()
    name                  = serializers.SerializerMethodField()
    last_login            = serializers.DateTimeField(read_only=True)
    tenant_name           = serializers.CharField(source='tenant.name',           read_only=True)
    tenant_phone          = serializers.CharField(source='tenant.phone',          read_only=True)
    tenant_address        = serializers.CharField(source='tenant.address',        read_only=True)
    tenant_vat_number     = serializers.CharField(source='tenant.vat_number',     read_only=True)
    tenant_receipt_footer = serializers.CharField(source='tenant.receipt_footer', read_only=True)
    tenant_currency       = serializers.CharField(source='tenant.currency',       read_only=True)
    tenant_language       = serializers.CharField(source='tenant.language',       read_only=True)
    tenant_show_tax_on_receipt = serializers.BooleanField(source='tenant.show_tax_on_receipt', read_only=True)
    tenant_scale_barcode_prefix = serializers.CharField(source='tenant.scale_barcode_prefix', read_only=True)
    tenant_logo           = serializers.SerializerMethodField()
    branch_name           = serializers.SerializerMethodField()
    terminal_name         = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'name',
            'role', 'is_active', 'last_login',
            'tenant',
            'tenant_name', 'tenant_phone', 'tenant_address', 'tenant_logo',
            'tenant_vat_number', 'tenant_receipt_footer',
            'tenant_currency', 'tenant_language', 'tenant_show_tax_on_receipt',
            'tenant_scale_barcode_prefix',
            'branch', 'branch_name',
            'terminal', 'terminal_name',
        ]
        read_only_fields = [
            'id', 'tenant',
            'tenant_name', 'tenant_phone', 'tenant_address', 'tenant_logo',
            'tenant_vat_number', 'tenant_receipt_footer',
            'tenant_currency', 'tenant_language', 'tenant_show_tax_on_receipt',
            'tenant_scale_barcode_prefix',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else ''

    def get_terminal_name(self, obj):
        return obj.terminal.name if obj.terminal else ''

    def get_tenant_logo(self, obj):
        logo = getattr(obj.tenant, 'logo', None) if obj.tenant_id else None
        if not logo:
            return None
        request = self.context.get('request')
        url = logo.url
        return request.build_absolute_uri(url) if request else url


def _split_name(name: str) -> tuple[str, str]:
    """Split a single "name" string into (first_name, last_name)."""
    parts = (name or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


class UserCreateSerializer(serializers.ModelSerializer):
    """Create-user payload from the team-management UI.

    The frontend posts a single `name` field plus `email`, `role`, `branch`,
    `pin_code`, and `is_active`. Username is derived from the email's
    local-part when not supplied; an internal random password is generated
    so the row still satisfies AbstractUser's password constraint — the user
    will authenticate via the PIN flow, not by knowing the password.
    """

    name      = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password  = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)
    pin_code  = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'name',
            'password', 'role', 'branch', 'terminal', 'pin_code', 'is_active',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'username': {'required': False, 'allow_blank': True},
            'email':    {'required': True},
        }

    def validate(self, attrs):
        # Derive username from the email local-part if the caller omitted it.
        username = (attrs.get('username') or '').strip()
        email    = (attrs.get('email') or '').strip()
        if not username and email:
            attrs['username'] = email.split('@', 1)[0]
        return attrs

    def create(self, validated_data):
        name = validated_data.pop('name', '') or ''
        if name and not validated_data.get('first_name'):
            first, last = _split_name(name)
            validated_data['first_name'] = first
            validated_data['last_name']  = last

        pin = validated_data.pop('pin_code', '') or ''
        password = validated_data.pop('password', '') or secrets.token_urlsafe(16)

        user = User(**validated_data)
        user.set_password(password)
        if pin:
            user.set_pin(pin)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    name     = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=6, required=False, allow_blank=True)
    pin_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = User
        fields = [
            'username', 'email', 'first_name', 'last_name', 'name',
            'password', 'role', 'branch', 'terminal', 'pin_code', 'is_active',
        ]
        extra_kwargs = {
            'username': {'required': False, 'allow_blank': True},
        }

    def update(self, instance, validated_data):
        name = validated_data.pop('name', None)
        if name is not None:
            first, last = _split_name(name)
            validated_data['first_name'] = first
            validated_data['last_name']  = last

        password = validated_data.pop('password', None)
        pin      = validated_data.pop('pin_code', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        if pin:
            instance.set_pin(pin)
        instance.save()
        return instance


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Serializer for the dedicated tenant-settings endpoint.

    Exposes business-facing tenant fields (name, contact, branding, receipt
    footer, locale) so a single GET/PATCH covers the Settings page. The logo
    is rendered as an absolute URL when the request context is available so
    the frontend can use it as an <img src>.
    """

    logo = serializers.ImageField(required=False, allow_null=True, use_url=True)

    class Meta:
        model  = Tenant
        fields = [
            'id', 'name',
            # Subscription (read-only — billing is managed elsewhere)
            'plan', 'trial_ends_at',
            # Store & receipt
            'phone', 'address', 'vat_number',
            'logo', 'receipt_footer', 'show_tax_on_receipt',
            # Localization
            'currency', 'language', 'timezone',
            # Hardware: printer
            'printer_name', 'printer_connection', 'printer_ip',
            # Hardware: scale
            'scale_barcode_prefix', 'scale_connection', 'scale_export_interval',
            # Payments
            'payment_cash_enabled', 'payment_card_enabled',
            'payment_wallet_enabled', 'card_terminal_type',
            'updated_at',
        ]
        read_only_fields = ['id', 'plan', 'trial_ends_at', 'updated_at']


# ── Finance master data (Phase 1.5 Slice C) ──────────────────────────────────


class FinancialAccountSerializer(serializers.ModelSerializer):
    """Tenant-scoped financial destination.

    `tenant` is set by the view from the authenticated user; `branch` (when
    provided) must belong to the same tenant. Cross-tenant linkage is the
    most common multi-tenant footgun, so we validate it explicitly rather
    than relying on PK uniqueness.
    """

    class Meta:
        model  = FinancialAccount
        fields = [
            'id', 'tenant', 'branch',
            'code', 'name', 'account_type',
            'currency', 'opening_balance',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']

    def validate_branch(self, branch):
        if branch is None:
            return branch
        tenant = self.context.get('tenant')
        if tenant is not None and branch.tenant_id != tenant.id:
            raise serializers.ValidationError(
                'Branch must belong to the caller\'s tenant.',
            )
        return branch

    def validate_code(self, code):
        """Surface the DB partial-UNIQUE (tenant, code) as a clean 400.

        Without this, a duplicate code would explode as IntegrityError → 500
        and (on Postgres) poison the request's transaction.
        """
        if not code:
            return code
        tenant = self.context.get('tenant')
        if tenant is None:
            return code
        qs = FinancialAccount.objects.filter(tenant=tenant, code=code)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f'A financial account with code {code!r} already exists in this tenant.',
            )
        return code


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Tenant-defined payment method.

    `requires_customer` is auto-true for `credit` on create unless the
    caller explicitly set it — credit sales always need a customer, so
    forgetting the flag silently would break Pay validation later.
    """

    class Meta:
        model  = PaymentMethod
        fields = [
            'id', 'tenant',
            'name', 'method_type', 'provider_name',
            'requires_customer', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']

    def validate_name(self, name):
        """Surface the DB UNIQUE (tenant, name) as a clean 400."""
        tenant = self.context.get('tenant')
        if tenant is None:
            return name
        qs = PaymentMethod.objects.filter(tenant=tenant, name=name)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f'A payment method named {name!r} already exists in this tenant.',
            )
        return name

    def validate(self, attrs):
        # `credit` methods always require a customer — overriding the user's
        # `requires_customer` value rather than 400-ing keeps the API
        # forgiving while the model.save() enforces the same invariant for
        # direct ORM writes. Applies on both create and PATCH.
        method_type = attrs.get(
            'method_type',
            getattr(self.instance, 'method_type', None),
        )
        if method_type == PaymentMethod.MethodType.CREDIT:
            attrs['requires_customer'] = True
        return attrs


# Compatibility matrix enforced by `BranchPaymentMethodSerializer.validate`.
# A method_type may only route into specific account_type(s); `custom` is
# unconstrained so tenants can model unusual scenarios.
#
# Cash → cashbox only. `main_safe` is intentionally NOT a valid direct POS
# destination: a main safe receives cash via cash-drops/internal transfers,
# never as the first landing point for a customer payment.
_METHOD_TO_DEST_ACCOUNT_TYPES = {
    PaymentMethod.MethodType.CASH:   {FinancialAccount.AccountType.CASHBOX},
    PaymentMethod.MethodType.CARD:   {FinancialAccount.AccountType.CARD_SETTLEMENT},
    PaymentMethod.MethodType.WALLET: {FinancialAccount.AccountType.WALLET},
    PaymentMethod.MethodType.CREDIT: {FinancialAccount.AccountType.CUSTOMER_AR},
}


class BranchPaymentMethodSerializer(serializers.ModelSerializer):
    """Per-branch enabled payment + routing config.

    Server-side validation enforces the contract intent: every FK must live
    in the caller's tenant, and the destination account type must be
    compatible with the method type (cash → cashbox/main_safe, card →
    card_settlement, wallet → wallet, credit → customer_ar). `custom`
    method type accepts any destination.

    `tenant` and `branch` are set by the view from the URL/auth context;
    the request body must not be allowed to spoof them.
    """

    payment_method_name        = serializers.CharField(source='payment_method.name',        read_only=True)
    payment_method_type        = serializers.CharField(source='payment_method.method_type', read_only=True)
    destination_account_name   = serializers.CharField(source='destination_account.name',   read_only=True)
    destination_account_type   = serializers.CharField(source='destination_account.account_type', read_only=True)

    class Meta:
        model  = BranchPaymentMethod
        fields = [
            'id', 'tenant', 'branch',
            'payment_method', 'payment_method_name', 'payment_method_type',
            'destination_account', 'destination_account_name', 'destination_account_type',
            'settlement_bank_account',
            'commission_percent', 'fixed_fee',
            'commission_expense_account',
            'is_default', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'branch', 'created_at', 'updated_at']

    # ── Per-field tenant scoping ──────────────────────────────────────────────

    def _check_tenant(self, obj, label):
        tenant = self.context.get('tenant')
        if tenant is not None and obj is not None and obj.tenant_id != tenant.id:
            raise serializers.ValidationError(
                f'{label} must belong to the caller\'s tenant.',
            )
        return obj

    def validate_payment_method(self, v):
        return self._check_tenant(v, 'payment_method')

    def validate_destination_account(self, v):
        return self._check_tenant(v, 'destination_account')

    def validate_settlement_bank_account(self, v):
        return self._check_tenant(v, 'settlement_bank_account')

    def validate_commission_expense_account(self, v):
        return self._check_tenant(v, 'commission_expense_account')

    # ── Cross-field rules ─────────────────────────────────────────────────────

    def validate(self, attrs):
        tenant = self.context.get('tenant')
        branch = self.context.get('branch') or getattr(self.instance, 'branch', None)

        # Resolve the effective method + destination after a possible PATCH.
        method = attrs.get('payment_method') or getattr(self.instance, 'payment_method', None)
        dest   = attrs.get('destination_account') or getattr(self.instance, 'destination_account', None)

        # Branch+method uniqueness — surface DB constraint as a clean 400.
        if tenant is not None and branch is not None and method is not None:
            qs = BranchPaymentMethod.objects.filter(
                tenant=tenant, branch=branch, payment_method=method,
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'payment_method': (
                        'This payment method is already enabled on this branch.'
                    ),
                })

        if method is None or dest is None:
            return attrs

        allowed = _METHOD_TO_DEST_ACCOUNT_TYPES.get(method.method_type)
        # `custom` (or unknown) → no restriction; tenants opt into whatever
        # routing makes sense for their business.
        if allowed and dest.account_type not in allowed:
            raise serializers.ValidationError({
                'destination_account': (
                    f'method_type={method.method_type!r} cannot route to '
                    f'account_type={dest.account_type!r}; allowed: '
                    f'{sorted(allowed)}'
                ),
            })

        # Settlement bank is only meaningful for card methods.
        settle = attrs.get('settlement_bank_account') or getattr(self.instance, 'settlement_bank_account', None)
        if settle is not None and settle.account_type != FinancialAccount.AccountType.BANK:
            raise serializers.ValidationError({
                'settlement_bank_account': (
                    'settlement_bank_account must be a bank account (account_type=bank).'
                ),
            })

        commission = attrs.get('commission_expense_account') or getattr(self.instance, 'commission_expense_account', None)
        if commission is not None and commission.account_type != FinancialAccount.AccountType.EXPENSE:
            raise serializers.ValidationError({
                'commission_expense_account': (
                    'commission_expense_account must be an expense account (account_type=expense).'
                ),
            })

        return attrs


# ── Customer + Supplier master data (Phase 1.5 Slice E) ─────────────────────


class _PartySerializerMixin:
    """Shared tenant scoping + code uniqueness for Customer/Supplier.

    Both party serializers expect `self.context['tenant']` to be set by
    the view (via `_TenantContextMixin` in views.py). Mixing in here keeps
    the per-field validation out of two identical implementations.
    """

    party_model = None  # subclasses override

    def validate_default_branch(self, branch):
        if branch is None:
            return branch
        tenant = self.context.get('tenant')
        if tenant is not None and branch.tenant_id != tenant.id:
            raise serializers.ValidationError(
                'default_branch must belong to the caller\'s tenant.',
            )
        return branch

    def validate_code(self, code):
        """Per-tenant uniqueness (partial — '' is allowed across rows)."""
        if not code:
            return code
        tenant = self.context.get('tenant')
        if tenant is None:
            return code
        qs = self.party_model.objects.filter(tenant=tenant, code=code)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f'A {self.party_model.__name__.lower()} with code {code!r} '
                f'already exists in this tenant.',
            )
        return code


class CustomerSerializer(_PartySerializerMixin, serializers.ModelSerializer):
    party_model = Customer

    class Meta:
        model  = Customer
        fields = [
            'id', 'tenant',
            'code', 'name', 'phone', 'email', 'tax_number',
            'default_branch', 'price_tier_id',
            'credit_limit', 'opening_balance',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class SupplierSerializer(_PartySerializerMixin, serializers.ModelSerializer):
    party_model = Supplier

    class Meta:
        model  = Supplier
        fields = [
            'id', 'tenant',
            'code', 'name', 'phone', 'email', 'tax_number',
            'default_branch',
            'opening_balance',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at', 'updated_at']


class FinancialAccountMovementSerializer(serializers.ModelSerializer):
    """Read-only ledger row.

    Writes go through `accounts.services.account_movements` — the API
    surface deliberately does not accept POSTs to this resource in this
    slice. `balance_after` is computed by the service, never trusted from
    a client.
    """

    account_name         = serializers.CharField(source='account.name',         read_only=True)
    account_type         = serializers.CharField(source='account.account_type', read_only=True)
    actor_user_username  = serializers.CharField(source='actor_user.username',  read_only=True)

    class Meta:
        model  = FinancialAccountMovement
        fields = [
            'id', 'tenant', 'branch',
            'account', 'account_name', 'account_type',
            'source_document_type', 'source_document_id',
            'movement_type',
            'debit', 'credit', 'balance_after', 'currency',
            'actor_user', 'actor_user_username',
            'terminal_id', 'shift_id',
            'occurred_at', 'notes', 'created_at',
        ]
        read_only_fields = fields


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['tenant_id'] = user.tenant_id
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data
