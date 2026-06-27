import secrets

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Branch, Tenant

User = get_user_model()


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Branch
        fields = ['id', 'name', 'address', 'phone', 'active', 'created_at']
        read_only_fields = ['id', 'created_at']


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
