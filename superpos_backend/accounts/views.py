import json

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Branch
from .permissions import IsCashierOrAbove, IsManagerOrAbove
from .serializers import (
    BranchSerializer,
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
