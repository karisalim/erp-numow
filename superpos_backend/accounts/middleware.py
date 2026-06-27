"""Tenant activation / subscription enforcement.

If a tenant is flagged inactive in the admin (`Tenant.active=False`) or the
trial window has elapsed, we want **every** subsequent authenticated API call
to fail fast with a 403 JSON the frontend can recognise — rather than letting
the user keep operating the POS with stale tokens.

The middleware also invalidates any outstanding refresh tokens for the
tenant's users so reissuing access tokens from another device is impossible
until the operator clears the flag again.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)

# Path prefixes the middleware never blocks. These are the auth surfaces
# users need even when their tenant is suspended (so they can refresh once
# and get the same 403 here, or log out cleanly), plus served media + admin.
EXEMPT_PREFIXES = (
    '/api/auth/login/',
    '/api/auth/token/',     # token/refresh/
    '/api/accounts/login/', # mirror mount
    '/api/accounts/token/',
    '/admin/',
    '/media/',
    '/static/',
)

BLOCK_PAYLOAD = {
    'code':  'SUBSCRIPTION_EXPIRED',
    'error': 'Your store account has been suspended or your subscription has expired.',
}


def _is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _blacklist_tenant_tokens(tenant_id: int) -> None:
    """Best-effort: blacklist every outstanding refresh token for this tenant.

    Stateless JWT access tokens can't be revoked server-side without a token
    blacklist, but rotating refresh tokens *can* — once their refresh is
    rejected, the user is fully out. Failure here is non-fatal; the middleware
    still returns 403 to the current request.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken, OutstandingToken,
        )
        outstanding = OutstandingToken.objects.filter(user__tenant_id=tenant_id)
        for token in outstanding.only('id', 'jti'):
            BlacklistedToken.objects.get_or_create(token=token)
    except Exception as exc:    # noqa: BLE001 — best-effort, never crashes the request
        logger.warning('Failed to blacklist tokens for tenant=%s: %s', tenant_id, exc)


class SubscriptionCheckMiddleware:
    """Hard-block requests for inactive or expired tenants."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only police the JSON API surface.
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        if _is_exempt(request.path):
            return self.get_response(request)

        user = self._resolve_user(request)
        if user is None:
            return self.get_response(request)
        if not getattr(user, 'is_authenticated', False):
            return self.get_response(request)
        if user.is_superuser:
            return self.get_response(request)

        tenant = getattr(user, 'tenant', None)
        if tenant is None:
            return self.get_response(request)

        if self._should_block(tenant):
            _blacklist_tenant_tokens(tenant.id)
            return JsonResponse(BLOCK_PAYLOAD, status=403)

        return self.get_response(request)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _should_block(tenant) -> bool:
        if not tenant.active:
            return True
        trial = getattr(tenant, 'trial_ends_at', None)
        if trial and trial < timezone.now():
            return True
        return False

    @staticmethod
    def _resolve_user(request):
        """DRF auth runs after view dispatch — peek at the JWT ourselves so we
        can block *before* the protected view runs. Falls back to whatever
        Django auth set on the request (anonymous → bypassed)."""
        if getattr(request, '_subscription_user', None) is not None:
            return request._subscription_user

        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False):
            request._subscription_user = user
            return user

        # No session — try the bearer token (the only auth we ship for /api/).
        auth = JWTAuthentication()
        try:
            header = auth.get_header(request)
            if header is None:
                return None
            raw = auth.get_raw_token(header)
            if raw is None:
                return None
            validated = auth.get_validated_token(raw)
            user = auth.get_user(validated)
            request._subscription_user = user
            return user
        except (InvalidToken, TokenError):
            return None
        except Exception:    # noqa: BLE001
            return None


# Suppress unused-import warning when DEBUG removes the import below.
_ = settings
