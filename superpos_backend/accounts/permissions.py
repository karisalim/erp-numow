from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

User = get_user_model()


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.OWNER
        )


class IsAdminOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.OWNER, User.Role.ADMIN)
        )


class IsManagerOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.OWNER, User.Role.ADMIN, User.Role.MANAGER)
        )


class IsCashierOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (
                User.Role.OWNER,
                User.Role.ADMIN,
                User.Role.MANAGER,
                User.Role.CASHIER,
            )
        )
