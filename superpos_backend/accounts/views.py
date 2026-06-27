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
    FinancialAccount,
    FinancialAccountMovement,
    PaymentMethod,
)
from .permissions import IsCashierOrAbove, IsManagerOrAbove
from .serializers import (
    BranchPaymentMethodSerializer,
    BranchSerializer,
    BranchSettingsSerializer,
    BranchUserAssignmentSerializer,
    BranchV2Serializer,
    CustomTokenObtainPairSerializer,
    FinancialAccountMovementSerializer,
    FinancialAccountSerializer,
    PaymentMethodSerializer,
    TenantSettingsSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
)
from .services import account_movements

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
    """GET /api/finance/accounts/{id}/movements/ — per-account statement."""

    http_method_names = ['get', 'head', 'options']

    def get(self, request, pk):
        tenant, account = self._account(request, pk)
        params = request.query_params

        branch_id = _parse_optional_int(params.get('branch'))
        branch = None
        if branch_id is not None:
            branch = Branch.objects.filter(tenant=tenant, pk=branch_id).first()
            if branch is None:
                raise NotFound('Branch not found.')

        qs = account_movements.get_account_statement(
            account,
            branch=branch,
            movement_type=params.get('movement_type') or None,
            source_document_type=params.get('source_document_type') or None,
            source_document_id=_parse_optional_int(params.get('source_document_id')),
            occurred_from=params.get('occurred_from') or None,
            occurred_to=params.get('occurred_to') or None,
        )
        return Response(FinancialAccountMovementSerializer(qs, many=True).data)


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
