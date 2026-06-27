import json

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Branch, BranchSettings, BranchUserAssignment
from .permissions import IsCashierOrAbove, IsManagerOrAbove
from .serializers import (
    BranchSerializer,
    BranchSettingsSerializer,
    BranchUserAssignmentSerializer,
    BranchV2Serializer,
    CustomTokenObtainPairSerializer,
    TenantSettingsSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
)

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
