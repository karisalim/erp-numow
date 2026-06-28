import json

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Branch,
    BranchPaymentMethod,
    BranchSettings,
    BranchUserAssignment,
    Customer,
    CustomerARMovement,
    CustomerReceipt,
    FinancialAccount,
    FinancialAccountMovement,
    PaymentMethod,
    Supplier,
    SupplierAPMovement,
    SupplierPayment,
)
from .permissions import IsCashierOrAbove, IsManagerOrAbove
from .serializers import (
    BranchPaymentMethodSerializer,
    BranchSerializer,
    BranchSettingsSerializer,
    BranchUserAssignmentSerializer,
    BranchV2Serializer,
    CustomerARMovementSerializer,
    CustomerReceiptSerializer,
    CustomerSerializer,
    CustomTokenObtainPairSerializer,
    FinancialAccountMovementSerializer,
    FinancialAccountSerializer,
    PaymentMethodSerializer,
    SupplierAPMovementSerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
    TenantSettingsSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
)
from .services import account_movements
from .services import customer_ar as customer_ar_svc
from .services import customer_receipts as customer_receipts_svc
from .services import supplier_ap as supplier_ap_svc
from .services import supplier_payments as supplier_payments_svc
from pos.services import idempotency

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsManagerOrAbove]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'role']
    ordering_fields = ['username', 'email', 'role', 'is_active']
    ordering = ['username']

    def get_queryset(self):
        return User.objects.filter(tenant=self.request.user.tenant)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class BranchListCreateView(generics.ListCreateAPIView):
    """List + create branches scoped to the caller's tenant."""

    serializer_class = BranchSerializer
    search_fields    = ['name', 'address']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        tenant = getattr(self.request.user, 'tenant', None)
        qs = Branch.objects.all()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

    def perform_create(self, serializer):
        tenant = getattr(self.request.user, 'tenant', None)
        serializer.save(tenant=tenant)


class BranchDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class   = BranchSerializer
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        tenant = getattr(self.request.user, 'tenant', None)
        qs = Branch.objects.all()
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs


class TenantSettingsView(generics.RetrieveUpdateAPIView):
    """GET / PATCH the calling user's tenant settings.

    Multipart parsing is enabled so the frontend can upload a logo via
    FormData while sending the other text fields in the same request.
    """

    serializer_class   = TenantSettingsSerializer
    permission_classes = [IsManagerOrAbove]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_object(self):
        tenant = getattr(self.request.user, 'tenant', None)
        if tenant is None:
            raise NotFound('This user is not associated with a tenant.')
        return tenant


SUPPORTED_LANGS = {'en', 'ar'}


def _flatten_strings(d, prefix=''):
    """Validate a translation dict — values must be strings, keys non-empty.

    Returns the same dict on success. Raises ValidationError otherwise. We
    only walk one level deep because react-i18next's flat-key style is what
    the frontend expects (`settings.tabs.store` lives as a single key).
    """
    if not isinstance(d, dict):
        raise ValidationError({'detail': 'Translation payload must be a JSON object.'})
    for k, v in d.items():
        if not isinstance(k, str) or not k.strip():
            raise ValidationError({'detail': f'{prefix}Key must be a non-empty string.'})
        if isinstance(v, dict):
            _flatten_strings(v, prefix=f'{k}.')
        elif not isinstance(v, str):
            raise ValidationError({'detail': f'{prefix}{k}: value must be a string.'})
    return d


class TenantTranslationsView(APIView):
    """Per-language translation overrides for the calling user's tenant.

    `GET    /tenant/translations/<lang>/`  → { language, overrides }   — cashier+
    `PUT    /tenant/translations/<lang>/`  → replace overrides         — manager+
    `DELETE /tenant/translations/<lang>/`  → clear overrides           — manager+

    PUT accepts either:
      - JSON body  (`Content-Type: application/json`) with the dict as the body, OR
      - Multipart with a `file` field containing a `.json` payload.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method in ('PUT', 'DELETE'):
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def _tenant(self):
        tenant = getattr(self.request.user, 'tenant', None)
        if tenant is None:
            raise NotFound('This user is not associated with a tenant.')
        return tenant

    def _check_lang(self, lang):
        if lang not in SUPPORTED_LANGS:
            raise ValidationError({'language': f'Unsupported language "{lang}".'})

    def get(self, request, lang):
        self._check_lang(lang)
        tenant = self._tenant()
        overrides = (tenant.translation_overrides or {}).get(lang, {})
        return Response({'language': lang, 'overrides': overrides, 'count': len(overrides)})

    def put(self, request, lang):
        self._check_lang(lang)
        tenant = self._tenant()

        # Accept either a JSON-body dict OR a multipart file upload.
        uploaded = request.FILES.get('file')
        if uploaded is not None:
            try:
                payload = json.loads(uploaded.read().decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError({'detail': f'Invalid JSON file: {exc}'}) from exc
        else:
            payload = request.data

        _flatten_strings(payload)

        overrides = dict(tenant.translation_overrides or {})
        overrides[lang] = payload
        tenant.translation_overrides = overrides
        tenant.save(update_fields=['translation_overrides', 'updated_at'])
        return Response({'language': lang, 'overrides': payload, 'count': len(payload)})

    def delete(self, request, lang):
        self._check_lang(lang)
        tenant = self._tenant()
        overrides = dict(tenant.translation_overrides or {})
        overrides.pop(lang, None)
        tenant.translation_overrides = overrides
        tenant.save(update_fields=['translation_overrides', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsManagerOrAbove]

    def get_queryset(self):
        return User.objects.filter(tenant=self.request.user.tenant)

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer


# ── /api/branches/ — v3.6 master-data surface (Phase 1.5 Slice A) ────────────

def _tenant_or_404(request):
    """Return the caller's tenant, or raise 404 if unattached.

    Centralizes the tenant-scoping check so every branch view fails the same
    way for a tenantless user. Returning 404 (vs. 400) hides the existence
    of foreign-tenant resources from probing.
    """
    tenant = getattr(request.user, 'tenant', None)
    if tenant is None:
        raise NotFound('User is not associated with a tenant.')
    return tenant


class BranchV2ListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/branches/ — tenant-scoped.

    Read open to any authenticated user in the tenant (cashiers need branch
    lists to know where they are); create/modify is manager+.
    """

    serializer_class = BranchV2Serializer
    search_fields    = ['name', 'code', 'address']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        return Branch.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = _tenant_or_404(self.request)
        serializer.save(tenant=tenant)


class BranchV2DetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/branches/{id}/ — no DELETE.

    Per MASTER_DATA_CONTRACT.md §4.2 a branch cannot be deleted; use the
    /deactivate/ action instead. `http_method_names` is the simplest guard.
    """

    serializer_class   = BranchV2Serializer
    permission_classes = [IsManagerOrAbove]
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        return Branch.objects.filter(tenant=tenant)


class BranchDeactivateView(APIView):
    """POST /api/branches/{id}/deactivate/ — flip `active` to False.

    Idempotent: calling it twice yields the same end state and a 200. The
    response mirrors the branch detail so the client can refresh state in
    one round-trip.
    """

    permission_classes = [IsManagerOrAbove]

    def post(self, request, pk):
        tenant = _tenant_or_404(request)
        branch = Branch.objects.filter(tenant=tenant, pk=pk).first()
        if branch is None:
            raise NotFound('Branch not found.')
        if branch.active:
            branch.active = False
            branch.save(update_fields=['active', 'updated_at'])
        return Response(BranchV2Serializer(branch).data)


class BranchSettingsView(APIView):
    """GET/PATCH /api/branches/{id}/settings/.

    Settings are created lazily on first GET — saves the caller from having
    to POST an empty document first. PATCH-only writes match the "partial
    update" semantics the contract describes ("PATCH").
    """

    permission_classes = [IsManagerOrAbove]

    def _branch(self, request, pk):
        tenant = _tenant_or_404(request)
        branch = Branch.objects.filter(tenant=tenant, pk=pk).first()
        if branch is None:
            raise NotFound('Branch not found.')
        return tenant, branch

    def _settings(self, tenant, branch):
        settings_obj, _ = BranchSettings.objects.get_or_create(
            branch=branch, defaults={'tenant': tenant},
        )
        return settings_obj

    def get(self, request, pk):
        tenant, branch = self._branch(request, pk)
        return Response(BranchSettingsSerializer(self._settings(tenant, branch)).data)

    def patch(self, request, pk):
        tenant, branch = self._branch(request, pk)
        settings_obj = self._settings(tenant, branch)
        serializer = BranchSettingsSerializer(
            settings_obj, data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class BranchUsersView(APIView):
    """GET/POST /api/branches/{id}/users/.

    GET → list of BranchUserAssignment rows for the branch.
    POST → create or reactivate an assignment. The body supplies `user`,
    optional `role_at_branch` (defaults to the user's current role),
    optional `is_default_branch`. `tenant` and `branch` are derived from
    the URL + auth and cannot be spoofed.

    Repeated POSTs with the same `user` are idempotent at the model level
    (unique constraint); the view returns 200 with the existing row instead
    of 409, to match the "assign or reassign" UX.
    """

    permission_classes = [IsManagerOrAbove]

    def _branch(self, request, pk):
        tenant = _tenant_or_404(request)
        branch = Branch.objects.filter(tenant=tenant, pk=pk).first()
        if branch is None:
            raise NotFound('Branch not found.')
        return tenant, branch

    def get(self, request, pk):
        tenant, branch = self._branch(request, pk)
        qs = BranchUserAssignment.objects.filter(tenant=tenant, branch=branch)
        return Response(BranchUserAssignmentSerializer(qs, many=True).data)

    def post(self, request, pk):
        tenant, branch = self._branch(request, pk)
        user_id = request.data.get('user')
        if not user_id:
            raise ValidationError({'user': 'This field is required.'})

        # Enforce tenant isolation: the target user must belong to the
        # caller's tenant, otherwise we'd happily wire users across tenants.
        target = User.objects.filter(tenant=tenant, pk=user_id).first()
        if target is None:
            raise NotFound('User not found in this tenant.')

        defaults = {
            'tenant':            tenant,
            'role_at_branch':    request.data.get('role_at_branch', target.role),
            'is_default_branch': bool(request.data.get('is_default_branch', False)),
            'is_active':         bool(request.data.get('is_active', True)),
        }
        assignment, created = BranchUserAssignment.objects.update_or_create(
            tenant=tenant, branch=branch, user=target,
            defaults=defaults,
        )
        return Response(
            BranchUserAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ── /api/finance/* — Financial Accounts + Payment Methods (Phase 1.5 Slice C) ─

class _TenantContextMixin:
    """Inject `tenant` into the serializer context for cross-tenant checks.

    `FinancialAccountSerializer` / `BranchPaymentMethodSerializer` look at
    `self.context['tenant']` to verify every FK lives in the caller's
    tenant. Centralizing the wiring keeps individual views terse.

    Works on both `GenericAPIView` (has `get_serializer_context`) and
    plain `APIView` (doesn't) by checking for the parent implementation.
    """

    def get_serializer_context(self):
        parent_getter = getattr(super(), 'get_serializer_context', None)
        ctx = parent_getter() if callable(parent_getter) else {
            'request':  getattr(self, 'request', None),
            'view':     self,
        }
        ctx['tenant'] = _tenant_or_404(self.request)
        return ctx


class FinancialAccountListCreateView(_TenantContextMixin, generics.ListCreateAPIView):
    serializer_class = FinancialAccountSerializer
    search_fields    = ['name', 'code']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        qs = FinancialAccount.objects.filter(tenant=tenant)
        account_type = self.request.query_params.get('account_type')
        if account_type:
            qs = qs.filter(account_type=account_type)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=_tenant_or_404(self.request))


class FinancialAccountDetailView(_TenantContextMixin, generics.RetrieveUpdateAPIView):
    serializer_class   = FinancialAccountSerializer
    permission_classes = [IsManagerOrAbove]
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return FinancialAccount.objects.filter(tenant=_tenant_or_404(self.request))


class FinancialAccountDeactivateView(APIView):
    """POST /api/finance/accounts/{id}/deactivate/.

    Idempotent flip of `is_active`. Hard-delete is deliberately not exposed
    because posted FinancialAccountMovements (later slices) will FK back to
    the row and PROTECT on delete.
    """

    permission_classes = [IsManagerOrAbove]

    def post(self, request, pk):
        tenant = _tenant_or_404(request)
        account = FinancialAccount.objects.filter(tenant=tenant, pk=pk).first()
        if account is None:
            raise NotFound('Financial account not found.')
        if account.is_active:
            account.is_active = False
            account.save(update_fields=['is_active', 'updated_at'])
        return Response(FinancialAccountSerializer(account).data)


class PaymentMethodListCreateView(_TenantContextMixin, generics.ListCreateAPIView):
    serializer_class = PaymentMethodSerializer
    search_fields    = ['name', 'method_type', 'provider_name']
    ordering         = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        return PaymentMethod.objects.filter(tenant=_tenant_or_404(self.request))

    def perform_create(self, serializer):
        serializer.save(tenant=_tenant_or_404(self.request))


class PaymentMethodDetailView(_TenantContextMixin, generics.RetrieveUpdateAPIView):
    serializer_class   = PaymentMethodSerializer
    permission_classes = [IsManagerOrAbove]
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return PaymentMethod.objects.filter(tenant=_tenant_or_404(self.request))


class PaymentMethodDeactivateView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request, pk):
        tenant = _tenant_or_404(request)
        method = PaymentMethod.objects.filter(tenant=tenant, pk=pk).first()
        if method is None:
            raise NotFound('Payment method not found.')
        if method.is_active:
            method.is_active = False
            method.save(update_fields=['is_active', 'updated_at'])
        return Response(PaymentMethodSerializer(method).data)


# ── /api/branches/{branch_id}/payment-methods/* ──────────────────────────────

class _BranchPaymentBaseView(_TenantContextMixin, APIView):
    """Shared lookup helpers for branch-scoped payment-method endpoints.

    The branch comes from the URL kwarg `branch_pk` and must belong to the
    caller's tenant (or it's a 404 — same hiding-by-default policy as the
    branch detail view).
    """

    permission_classes = [IsManagerOrAbove]

    def _branch(self, request, branch_pk):
        tenant = _tenant_or_404(request)
        branch = Branch.objects.filter(tenant=tenant, pk=branch_pk).first()
        if branch is None:
            raise NotFound('Branch not found.')
        return tenant, branch

    def _link(self, tenant, branch, pk):
        link = BranchPaymentMethod.objects.filter(
            tenant=tenant, branch=branch, pk=pk,
        ).first()
        if link is None:
            raise NotFound('Branch payment method not found.')
        return link


def _ctx_with_branch(view, branch):
    """Helper: serializer context augmented with the branch.

    BranchPaymentMethodSerializer.validate() reads both tenant + branch
    from context to enforce per-branch uniqueness without round-tripping
    through the DB unique constraint (which would surface as a 500).
    """
    ctx = view.get_serializer_context()
    ctx['branch'] = branch
    return ctx


class BranchPaymentMethodListCreateView(_BranchPaymentBaseView):
    def get(self, request, branch_pk):
        tenant, branch = self._branch(request, branch_pk)
        qs = BranchPaymentMethod.objects.filter(tenant=tenant, branch=branch)
        return Response(
            BranchPaymentMethodSerializer(
                qs, many=True, context=_ctx_with_branch(self, branch),
            ).data,
        )

    def post(self, request, branch_pk):
        tenant, branch = self._branch(request, branch_pk)
        serializer = BranchPaymentMethodSerializer(
            data=request.data, context=_ctx_with_branch(self, branch),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant, branch=branch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BranchPaymentMethodDetailView(_BranchPaymentBaseView):
    http_method_names = ['patch', 'head', 'options']

    def patch(self, request, branch_pk, pk):
        tenant, branch = self._branch(request, branch_pk)
        link = self._link(tenant, branch, pk)
        serializer = BranchPaymentMethodSerializer(
            link, data=request.data, partial=True,
            context=_ctx_with_branch(self, branch),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class BranchPaymentMethodDeactivateView(_BranchPaymentBaseView):
    http_method_names = ['post', 'head', 'options']

    def post(self, request, branch_pk, pk):
        tenant, branch = self._branch(request, branch_pk)
        link = self._link(tenant, branch, pk)
        if link.is_active:
            link.is_active = False
            link.save(update_fields=['is_active', 'updated_at'])
        return Response(
            BranchPaymentMethodSerializer(
                link, context=_ctx_with_branch(self, branch),
            ).data,
        )


# ── /api/finance/movements + per-account read endpoints (Slice D) ────────────

def _parse_optional_int(value):
    """Strict optional int parse — empty string / None → None, else int."""
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({'detail': f'Expected integer, got {value!r}.'})


class FinancialAccountMovementListView(generics.ListAPIView):
    """GET /api/finance/movements/ — flat tenant-wide ledger stream.

    Query params:
        account=<id>             filter to one account
        branch=<id>              filter to one branch
        movement_type=<type>     enum filter
        source_document_type=<s> filter on opaque source string
        source_document_id=<id>  filter on opaque source id
    """

    serializer_class   = FinancialAccountMovementSerializer
    permission_classes = [IsManagerOrAbove]
    ordering           = ['-id']

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        qs = FinancialAccountMovement.objects.filter(tenant=tenant)
        params = self.request.query_params

        account_id = _parse_optional_int(params.get('account'))
        if account_id is not None:
            qs = qs.filter(account_id=account_id)
        branch_id = _parse_optional_int(params.get('branch'))
        if branch_id is not None:
            qs = qs.filter(branch_id=branch_id)
        if mt := params.get('movement_type'):
            qs = qs.filter(movement_type=mt)
        if sdt := params.get('source_document_type'):
            qs = qs.filter(source_document_type=sdt)
        sdi = _parse_optional_int(params.get('source_document_id'))
        if sdi is not None:
            qs = qs.filter(source_document_id=sdi)
        return qs.order_by('id')


class _AccountScopedView(APIView):
    """Shared lookup for endpoints rooted at /finance/accounts/{id}/..."""

    permission_classes = [IsManagerOrAbove]

    def _account(self, request, pk):
        tenant = _tenant_or_404(request)
        account = FinancialAccount.objects.filter(tenant=tenant, pk=pk).first()
        if account is None:
            raise NotFound('Financial account not found.')
        return tenant, account


class FinancialAccountStatementView(_AccountScopedView):
    """GET /api/finance/accounts/{id}/movements/ — per-account statement.

    Returns the summary envelope (opening/closing balance, totals, filters,
    date range) plus the row list — see `_serialize_statement_summary`.
    Honors the standard filter set: branch / movement_type /
    source_document_type / source_document_id / actor_user /
    date_from / date_to.
    """

    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, account = self._account(request, pk)
        filters = _statement_filter_kwargs(request, tenant)
        summary = account_movements.get_account_statement_summary(
            account, **filters,
        )
        return Response(_serialize_statement_summary(
            summary, movement_serializer=FinancialAccountMovementSerializer,
        ))


# ── Customer + Supplier endpoints (Phase 1.5 Slice E) ───────────────────────

class _PartyListCreateView(_TenantContextMixin, generics.ListCreateAPIView):
    """Generic list/create for a tenant-scoped party (Customer/Supplier).

    Subclass overrides `model` + `serializer_class` (and `search_fields`).
    Cashier+ can list; manager+ can write. Inactive rows surface in the
    list — clients filter via `?is_active=true` if they want only live
    records.
    """

    model = None
    ordering = ['name']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsManagerOrAbove()]
        return [IsCashierOrAbove()]

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        qs = self.model.objects.filter(tenant=tenant)
        is_active = self.request.query_params.get('is_active')
        if is_active in ('true', '1'):
            qs = qs.filter(is_active=True)
        elif is_active in ('false', '0'):
            qs = qs.filter(is_active=False)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=_tenant_or_404(self.request))


class _PartyDetailView(_TenantContextMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH only — DELETE is intentionally absent (use deactivate)."""

    model = None
    permission_classes = [IsManagerOrAbove]
    http_method_names  = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return self.model.objects.filter(tenant=_tenant_or_404(self.request))


class _PartyDeactivateView(APIView):
    """POST /.../{id}/deactivate/ — idempotent flip of `is_active=False`."""

    model = None
    permission_classes = [IsManagerOrAbove]
    serializer_class = None

    def post(self, request, pk):
        tenant = _tenant_or_404(request)
        obj = self.model.objects.filter(tenant=tenant, pk=pk).first()
        if obj is None:
            raise NotFound(f'{self.model.__name__} not found.')
        if obj.is_active:
            obj.is_active = False
            obj.save(update_fields=['is_active', 'updated_at'])
        return Response(self.serializer_class(obj).data)


# Customer concrete views ────────────────────────────────────────────────────

class CustomerListCreateView(_PartyListCreateView):
    model            = Customer
    serializer_class = CustomerSerializer
    search_fields    = ['name', 'code', 'phone', 'email', 'tax_number']


class CustomerDetailView(_PartyDetailView):
    model            = Customer
    serializer_class = CustomerSerializer


class CustomerDeactivateView(_PartyDeactivateView):
    model            = Customer
    serializer_class = CustomerSerializer


# Supplier concrete views ────────────────────────────────────────────────────

class SupplierListCreateView(_PartyListCreateView):
    model            = Supplier
    serializer_class = SupplierSerializer
    search_fields    = ['name', 'code', 'phone', 'email', 'tax_number']


class SupplierDetailView(_PartyDetailView):
    model            = Supplier
    serializer_class = SupplierSerializer


class SupplierDeactivateView(_PartyDeactivateView):
    model            = Supplier
    serializer_class = SupplierSerializer


# ── Party AR / AP statement + balance + flat list (Phase 1.5 Slice F) ──────

class _PartyScopedReadView(APIView):
    """Shared lookup for endpoints rooted at /<party>/{id}/...

    Subclasses set `party_model` to Customer or Supplier. Returns 404 for
    foreign-tenant ids so existence never leaks across tenants.
    """

    permission_classes = [IsManagerOrAbove]
    party_model = None
    party_label = ''       # 'customer' / 'supplier' — used in 404 text

    def _party(self, request, pk):
        tenant = _tenant_or_404(request)
        obj = self.party_model.objects.filter(tenant=tenant, pk=pk).first()
        if obj is None:
            raise NotFound(f'{self.party_label.capitalize()} not found.')
        return tenant, obj


def _statement_filter_kwargs(request, tenant):
    """Pull the standard statement query params out of `request`.

    Returns a dict matching the keyword args of `get_*_statement`. Resolves
    the optional `?branch=<id>` against the caller's tenant (foreign branch
    id → 404). Also accepts the new aliases `date_from` / `date_to` as
    synonyms for `occurred_from` / `occurred_to` so the statement contract
    can use the natural name without breaking older callers.
    """
    params = request.query_params

    branch = None
    branch_id = _parse_optional_int(params.get('branch'))
    if branch_id is not None:
        branch = Branch.objects.filter(tenant=tenant, pk=branch_id).first()
        if branch is None:
            raise NotFound('Branch not found.')

    actor_user = None
    actor_user_id = _parse_optional_int(params.get('actor_user'))
    if actor_user_id is not None:
        actor_user = User.objects.filter(tenant=tenant, pk=actor_user_id).first()
        if actor_user is None:
            raise NotFound('User not found.')

    return {
        'branch':               branch,
        'movement_type':        params.get('movement_type') or None,
        'source_document_type': params.get('source_document_type') or None,
        'source_document_id':   _parse_optional_int(params.get('source_document_id')),
        'actor_user':           actor_user,
        # Accept both `occurred_from`/`occurred_to` (legacy) and
        # `date_from`/`date_to` (the v3.6 statement-contract name).
        'occurred_from':        (
            params.get('occurred_from') or params.get('date_from') or None
        ),
        'occurred_to':          (
            params.get('occurred_to') or params.get('date_to') or None
        ),
    }


def _serialize_statement_summary(summary, *, movement_serializer):
    """Convert a service-layer summary dict into a JSON-ready response body.

    The service returns Decimals + a queryset + raw datetime/None values;
    the API surface needs strings for money, ISO-8601 timestamps, and the
    serialized movement rows. Centralised so finance/AR/AP endpoints have
    one consistent shape.
    """
    def _dec(v):
        return str(v) if v is not None else None

    def _dt(v):
        if v is None:
            return None
        # Echo whatever the client sent — already a string. If a datetime
        # ever leaks through, render it ISO-8601.
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return str(v)

    return {
        'opening_balance': _dec(summary['opening_balance']),
        'total_debit':     _dec(summary['total_debit']),
        'total_credit':    _dec(summary['total_credit']),
        'net_change':      _dec(summary['net_change']),
        'closing_balance': _dec(summary['closing_balance']),
        'date_from':       _dt(summary['date_from']),
        'date_to':         _dt(summary['date_to']),
        'filters':         summary['filters'],
        'movements':       movement_serializer(summary['movements'], many=True).data,
    }


# Customer AR ────────────────────────────────────────────────────────────────

class CustomerStatementView(_PartyScopedReadView):
    """GET /api/customers/{id}/statement/ — per-customer AR statement.

    Returns the same summary envelope as the finance/account statement —
    opening_balance, total_debit, total_credit, net_change,
    closing_balance, date_from, date_to, filters, movements.
    """

    party_model = Customer
    party_label = 'customer'
    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, customer = self._party(request, pk)
        filters = _statement_filter_kwargs(request, tenant)
        summary = customer_ar_svc.get_customer_statement_summary(
            customer, **filters,
        )
        return Response(_serialize_statement_summary(
            summary, movement_serializer=CustomerARMovementSerializer,
        ))


class CustomerBalanceView(_PartyScopedReadView):
    """GET /api/customers/{id}/balance/ — derived current AR balance."""

    party_model = Customer
    party_label = 'customer'
    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, customer = self._party(request, pk)
        balance = customer_ar_svc.get_customer_balance(customer)
        return Response({
            'customer_id':     customer.id,
            'customer_name':   customer.name,
            'opening_balance': str(customer.opening_balance),
            'balance':         str(balance),
        })


class CustomerARMovementListView(generics.ListAPIView):
    """GET /api/customer-ar/movements/ — tenant-wide flat stream.

    Useful for admin auditing across customers. Supports `customer=<id>`,
    `branch=<id>`, `movement_type=`, `source_document_type=`,
    `source_document_id=` query params.
    """

    serializer_class   = CustomerARMovementSerializer
    permission_classes = [IsManagerOrAbove]
    ordering           = ['-id']

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        qs = CustomerARMovement.objects.filter(tenant=tenant)
        params = self.request.query_params

        if cid := _parse_optional_int(params.get('customer')):
            qs = qs.filter(customer_id=cid)
        if bid := _parse_optional_int(params.get('branch')):
            qs = qs.filter(branch_id=bid)
        if mt := params.get('movement_type'):
            qs = qs.filter(movement_type=mt)
        if sdt := params.get('source_document_type'):
            qs = qs.filter(source_document_type=sdt)
        if sdi := _parse_optional_int(params.get('source_document_id')):
            qs = qs.filter(source_document_id=sdi)
        return qs.order_by('id')


# Supplier AP ────────────────────────────────────────────────────────────────

class SupplierStatementView(_PartyScopedReadView):
    """GET /api/suppliers/{id}/statement/ — per-supplier AP statement.

    Returns the same summary envelope as the AR statement — see
    `CustomerStatementView`. AP is liability-like so `net_change`
    uses credit - debit (settled in the service layer).
    """

    party_model = Supplier
    party_label = 'supplier'
    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, supplier = self._party(request, pk)
        filters = _statement_filter_kwargs(request, tenant)
        summary = supplier_ap_svc.get_supplier_statement_summary(
            supplier, **filters,
        )
        return Response(_serialize_statement_summary(
            summary, movement_serializer=SupplierAPMovementSerializer,
        ))


class SupplierBalanceView(_PartyScopedReadView):
    """GET /api/suppliers/{id}/balance/ — derived current AP balance."""

    party_model = Supplier
    party_label = 'supplier'
    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, supplier = self._party(request, pk)
        balance = supplier_ap_svc.get_supplier_balance(supplier)
        return Response({
            'supplier_id':     supplier.id,
            'supplier_name':   supplier.name,
            'opening_balance': str(supplier.opening_balance),
            'balance':         str(balance),
        })


class SupplierAPMovementListView(generics.ListAPIView):
    """GET /api/supplier-ap/movements/ — tenant-wide flat stream."""

    serializer_class   = SupplierAPMovementSerializer
    permission_classes = [IsManagerOrAbove]
    ordering           = ['-id']

    def get_queryset(self):
        tenant = _tenant_or_404(self.request)
        qs = SupplierAPMovement.objects.filter(tenant=tenant)
        params = self.request.query_params

        if sid := _parse_optional_int(params.get('supplier')):
            qs = qs.filter(supplier_id=sid)
        if bid := _parse_optional_int(params.get('branch')):
            qs = qs.filter(branch_id=bid)
        if mt := params.get('movement_type'):
            qs = qs.filter(movement_type=mt)
        if sdt := params.get('source_document_type'):
            qs = qs.filter(source_document_type=sdt)
        if sdi := _parse_optional_int(params.get('source_document_id')):
            qs = qs.filter(source_document_id=sdi)
        return qs.order_by('id')


class FinancialAccountBalanceView(_AccountScopedView):
    """GET /api/finance/accounts/{id}/balance/ — derived current balance."""

    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, account = self._account(request, pk)
        balance = account_movements.get_account_current_balance(account)
        return Response({
            'account_id':      account.id,
            'account_type':    account.account_type,
            'currency':        account.currency,
            'opening_balance': str(account.opening_balance),
            'balance':         str(balance),
        })


# ── Settlement endpoints (Phase 1.5 Slice G) ────────────────────────────────
#
# CustomerReceipt + SupplierPayment POSTs hand off to the dedicated
# posting services — never to `serializer.save()` directly — so the
# document and ledger rows always travel together inside one atomic
# transaction. POST also supports `Idempotency-Key`: replaying the same
# key + payload returns the stored response; reusing the key with a
# different payload returns 409 (per API_CONTRACT.md §2). DELETE is
# deliberately not exposed; reversal is a future compensating-document
# slice, not a row mutation.


def _resolve_party_fk(model, *, tenant, pk, label):
    """Look up `model.id=pk` within the caller's tenant or raise 400.

    The serializer would normally do this via its FK field's queryset, but
    we look up parties before the serializer runs so the posting service
    receives actual model instances, not raw ids. Foreign-tenant ids
    raise ValidationError (400) rather than NotFound (404) because the
    request is well-formed but the referenced row is unreachable.
    """
    if pk in (None, ''):
        raise ValidationError({label: 'This field is required.'})
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        raise ValidationError({label: 'Must be an integer id.'})
    obj = model.objects.filter(tenant=tenant, pk=pk_int).first()
    if obj is None:
        raise ValidationError({label: f'{model.__name__} not found in this tenant.'})
    return obj


def _resolve_branch_fk(*, tenant, pk):
    """Optional branch — null is allowed (tenant-wide receipt)."""
    if pk in (None, ''):
        return None
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        raise ValidationError({'branch': 'Must be an integer id.'})
    branch = Branch.objects.filter(tenant=tenant, pk=pk_int).first()
    if branch is None:
        raise ValidationError({'branch': 'Branch not found in this tenant.'})
    return branch


class _SettlementListCreateBase(APIView):
    """Shared POST-with-idempotency + GET list scaffolding.

    Subclasses set `model`, `serializer_class`, `post_endpoint_label`
    (for the idempotency record path field), and override `_create()` to
    call the right posting service.
    """

    permission_classes = [IsCashierOrAbove]
    model = None
    serializer_class = None
    post_endpoint_label = ''

    # ── List ──────────────────────────────────────────────────────────────────

    def get_queryset(self, tenant, params):
        qs = self.model.objects.filter(tenant=tenant)
        bid = _parse_optional_int(params.get('branch'))
        if bid is not None:
            qs = qs.filter(branch_id=bid)
        return qs.order_by('-id')

    def get(self, request):
        tenant = _tenant_or_404(request)
        qs = self.get_queryset(tenant, request.query_params)
        return Response(self.serializer_class(qs, many=True).data)

    # ── Create ────────────────────────────────────────────────────────────────

    def _create(self, *, tenant, request, data):
        """Subclass hook — must return a serialized response body."""
        raise NotImplementedError

    def post(self, request):
        tenant = _tenant_or_404(request)
        key = (request.headers.get('Idempotency-Key') or '').strip()
        payload = request.data

        # Hardening fix: settlement posting is a financial side-effect, so
        # the Idempotency-Key header is REQUIRED (per API_CONTRACT.md §2).
        # A missing key would let a client retry on a flaky network and
        # post the same receipt/payment twice.
        if not key:
            return Response(
                {
                    'error': {
                        'code': 'IDEMPOTENCY_KEY_REQUIRED',
                        'detail': 'Idempotency-Key header is required for this endpoint.',
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Idempotency check — proceed / replay / conflict.
        lookup = idempotency.lookup(
            tenant=tenant, key=key, payload=payload,
            method=request.method, path=request.path, user=request.user,
        )
        if lookup.conflict:
            return Response(
                {
                    'error': {
                        'code': 'IDEMPOTENCY_CONFLICT',
                        'detail': (
                            f'Idempotency-Key {key!r} reused with a different payload.'
                        ),
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        if lookup.replay:
            return Response(lookup.body, status=lookup.status)

        body = self._create(tenant=tenant, request=request, data=payload)
        response = Response(body, status=status.HTTP_201_CREATED)

        # Persist the snapshot only after the work has succeeded so that a
        # later replay returns the same 201 with the same body. Failure
        # paths above (raised before this point) never write a snapshot,
        # so the next legitimate attempt with the same key can retry.
        idempotency.save(
            tenant=tenant, key=key, payload=payload,
            method=request.method, path=request.path, user=request.user,
            response_status=response.status_code, response_body=body,
        )
        return response


class _SettlementDetailBase(APIView):
    """Shared GET-detail scaffolding for settlement documents."""

    permission_classes = [IsCashierOrAbove]
    model = None
    serializer_class = None

    def get(self, request, pk):
        tenant = _tenant_or_404(request)
        obj = self.model.objects.filter(tenant=tenant, pk=pk).first()
        if obj is None:
            raise NotFound(f'{self.model.__name__} not found.')
        return Response(self.serializer_class(obj).data)


# Customer receipts ──────────────────────────────────────────────────────────

class CustomerReceiptListCreateView(_SettlementListCreateBase):
    """GET/POST /api/customer-receipts/.

    GET supports `?branch=<id>` filter; POST accepts the standard
    receipt payload + an `Idempotency-Key` header.
    """

    model               = CustomerReceipt
    serializer_class    = CustomerReceiptSerializer
    post_endpoint_label = 'customer-receipts'

    def get_queryset(self, tenant, params):
        qs = super().get_queryset(tenant, params)
        if cid := _parse_optional_int(params.get('customer')):
            qs = qs.filter(customer_id=cid)
        return qs

    def _create(self, *, tenant, request, data):
        # Resolve every FK against the caller's tenant before handing the
        # service real model instances. Looking these up here (rather
        # than via DRF FK fields) gives us a single tenant-scoping
        # checkpoint and lets the service stay decoupled from DRF.
        customer = _resolve_party_fk(
            Customer, tenant=tenant, pk=data.get('customer'), label='customer',
        )
        payment_method = _resolve_party_fk(
            PaymentMethod, tenant=tenant, pk=data.get('payment_method'),
            label='payment_method',
        )
        destination_account = _resolve_party_fk(
            FinancialAccount, tenant=tenant, pk=data.get('destination_account'),
            label='destination_account',
        )
        branch = _resolve_branch_fk(tenant=tenant, pk=data.get('branch'))

        try:
            receipt = customer_receipts_svc.create_customer_receipt(
                tenant=tenant,
                branch=branch,
                customer=customer,
                payment_method=payment_method,
                destination_account=destination_account,
                amount=data.get('amount'),
                reference=(data.get('reference') or ''),
                notes=(data.get('notes') or ''),
                actor_user=getattr(request, 'user', None),
            )
        except customer_receipts_svc.CustomerReceiptError as exc:
            raise ValidationError({'detail': str(exc)})

        return CustomerReceiptSerializer(receipt).data


class CustomerReceiptDetailView(_SettlementDetailBase):
    """GET /api/customer-receipts/{id}/ — read-only."""

    model            = CustomerReceipt
    serializer_class = CustomerReceiptSerializer
    http_method_names = ['get', 'head', 'options']


# Supplier payments ──────────────────────────────────────────────────────────

class SupplierPaymentListCreateView(_SettlementListCreateBase):
    """GET/POST /api/supplier-payments/."""

    model               = SupplierPayment
    serializer_class    = SupplierPaymentSerializer
    post_endpoint_label = 'supplier-payments'

    def get_queryset(self, tenant, params):
        qs = super().get_queryset(tenant, params)
        if sid := _parse_optional_int(params.get('supplier')):
            qs = qs.filter(supplier_id=sid)
        return qs

    def _create(self, *, tenant, request, data):
        supplier = _resolve_party_fk(
            Supplier, tenant=tenant, pk=data.get('supplier'), label='supplier',
        )
        payment_method = _resolve_party_fk(
            PaymentMethod, tenant=tenant, pk=data.get('payment_method'),
            label='payment_method',
        )
        source_account = _resolve_party_fk(
            FinancialAccount, tenant=tenant, pk=data.get('source_account'),
            label='source_account',
        )
        branch = _resolve_branch_fk(tenant=tenant, pk=data.get('branch'))

        try:
            payment = supplier_payments_svc.create_supplier_payment(
                tenant=tenant,
                branch=branch,
                supplier=supplier,
                payment_method=payment_method,
                source_account=source_account,
                amount=data.get('amount'),
                reference=(data.get('reference') or ''),
                notes=(data.get('notes') or ''),
                actor_user=getattr(request, 'user', None),
            )
        except supplier_payments_svc.SupplierPaymentError as exc:
            raise ValidationError({'detail': str(exc)})

        return SupplierPaymentSerializer(payment).data


class SupplierPaymentDetailView(_SettlementDetailBase):
    """GET /api/supplier-payments/{id}/ — read-only."""

    model            = SupplierPayment
    serializer_class = SupplierPaymentSerializer
    http_method_names = ['get', 'head', 'options']
