"""Access control for document-level permissions."""

from __future__ import annotations

from typing import Any

from quantumrag.core.logging import get_logger

logger = get_logger("quantumrag.security.acl")

# Metadata keys used for ACL
ACL_ROLES_KEY = "acl_roles"
ACL_USERS_KEY = "acl_users"


class ACLFilter:
    """Filter search results based on user permissions.

    Documents can have ACL metadata specifying which roles and/or users
    can access them. If no ACL metadata is present, the document is
    considered public (accessible to all).
    """

    def __init__(self) -> None:
        pass

    def apply(
        self,
        results: list[Any],
        user_roles: list[str] | None = None,
        user_id: str | None = None,
    ) -> list[Any]:
        """Filter results to only those the user can access.

        Args:
            results: List of result objects with a .metadata dict attribute,
                     or dicts with a "metadata" key.
            user_roles: Roles the current user has (e.g., ["admin", "engineering"]).
            user_id: The current user's ID.

        Returns:
            Filtered list containing only accessible results.
        """
        if not user_roles and not user_id:
            # No identity provided — return all (no filtering)
            return results

        filtered = []
        for result in results:
            metadata = self._get_metadata(result)
            if self._is_accessible(metadata, user_roles, user_id):
                filtered.append(result)

        logger.debug(
            "acl_filter_applied",
            total=len(results),
            allowed=len(filtered),
            user_id=user_id,
            roles=user_roles,
        )

        return filtered

    def _get_metadata(self, result: Any) -> dict[str, Any]:
        """Extract metadata from a result object or dict."""
        if isinstance(result, dict):
            return result.get("metadata", {})
        return getattr(result, "metadata", {})

    def _is_accessible(
        self,
        metadata: dict[str, Any],
        user_roles: list[str] | None,
        user_id: str | None,
    ) -> bool:
        """Check if a document is accessible to the given user."""
        acl_roles = metadata.get(ACL_ROLES_KEY)
        acl_users = metadata.get(ACL_USERS_KEY)

        # No ACL metadata means public access
        if not acl_roles and not acl_users:
            return True

        # Check user ID
        if user_id and acl_users and user_id in acl_users:
            return True

        # Check roles
        return bool(user_roles and acl_roles and set(user_roles) & set(acl_roles))

    @staticmethod
    def create_acl_metadata(
        roles: list[str] | None = None,
        users: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create ACL metadata dict for a document.

        Args:
            roles: List of roles that can access the document.
            users: List of user IDs that can access the document.

        Returns:
            Dict suitable for inclusion in document metadata.
        """
        acl: dict[str, Any] = {}
        if roles:
            acl[ACL_ROLES_KEY] = list(roles)
        if users:
            acl[ACL_USERS_KEY] = list(users)
        return acl
