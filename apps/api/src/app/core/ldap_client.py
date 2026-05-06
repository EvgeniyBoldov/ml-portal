"""
LDAP client for authentication and user lookup.

Pure Python implementation using ldap3 (no system dependencies).
Supports Active Directory with configurable attributes.
"""
from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any

from ldap3 import Server, Connection, ALL, Tls, AUTO_BIND_NO_TLS
from ldap3.core.exceptions import LDAPException, LDAPBindError, LDAPSocketOpenError

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LDAPUserProfile:
    """Normalized user profile from LDAP."""
    login: str
    email: str | None
    full_name: str | None
    external_id: str  # LDAP DN
    groups: list[str]
    is_active: bool  # Based on userAccountControl


@dataclass(frozen=True)
class LDAPAuthResult:
    """Result of LDAP authentication attempt."""
    success: bool
    user: LDAPUserProfile | None = None
    error: str | None = None


class LDAPClient:
    """LDAP client for AD/LDAP authentication and user operations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._server: Server | None = None
        self._service_conn: Connection | None = None

    def _get_server(self) -> Server:
        """Get or create LDAP server instance."""
        if self._server is None:
            tls = None
            if self.settings.AUTH_LDAP_USE_TLS:
                tls_kwargs: dict[str, Any] = {"validate": ssl.CERT_REQUIRED if self.settings.AUTH_LDAP_TLS_VERIFY else ssl.CERT_NONE}
                if self.settings.AUTH_LDAP_TLS_CA_FILE:
                    tls_kwargs["ca_certs_file"] = self.settings.AUTH_LDAP_TLS_CA_FILE
                tls = Tls(**tls_kwargs)

            self._server = Server(
                self.settings.AUTH_LDAP_SERVER_URI or "ldap://localhost:389",
                get_info=ALL,
                use_ssl=self.settings.AUTH_LDAP_USE_TLS and self.settings.AUTH_LDAP_SERVER_URI and self.settings.AUTH_LDAP_SERVER_URI.startswith("ldaps://"),
                tls=tls if tls else None,
                connect_timeout=self.settings.AUTH_LDAP_TIMEOUT_SECONDS,
            )
        return self._server

    def _get_service_connection(self) -> Connection | None:
        """Get connection bound with service account."""
        if not self.settings.AUTH_LDAP_BIND_DN or not self.settings.AUTH_LDAP_BIND_PASSWORD:
            logger.debug("LDAP service credentials not configured")
            return None

        try:
            conn = Connection(
                self._get_server(),
                user=self.settings.AUTH_LDAP_BIND_DN,
                password=self.settings.AUTH_LDAP_BIND_PASSWORD,
                auto_bind=AUTO_BIND_NO_TLS if not self.settings.AUTH_LDAP_USE_TLS else True,
                receive_timeout=self.settings.AUTH_LDAP_TIMEOUT_SECONDS,
            )
            if self.settings.AUTH_LDAP_USE_TLS and not conn.start_tls():
                logger.warning("LDAP StartTLS failed")
            return conn
        except LDAPException as exc:
            logger.warning(f"LDAP service bind failed: {exc}")
            return None

    def _build_user_filter(self, login: str) -> str:
        """Build LDAP filter for user search."""
        template = self.settings.AUTH_LDAP_USER_SEARCH_FILTER
        # Escape special LDAP characters in login
        safe_login = login.replace("\\", "\\5c").replace("*", "\\2a").replace("(", "\\28").replace(")", "\\29").replace("\x00", "\\00")
        return template.format(login=safe_login)

    def _parse_user_entry(self, entry: Any, login: str) -> LDAPUserProfile | None:
        """Parse LDAP entry into user profile."""
        if not entry or not entry.entry_dn:
            return None

        attrs = entry.entry_attributes_as_dict

        # Get email
        email_attr = self.settings.AUTH_LDAP_USER_EMAIL_ATTR
        email = None
        if email_attr in attrs and attrs[email_attr]:
            email = attrs[email_attr][0] if isinstance(attrs[email_attr], list) else attrs[email_attr]

        # Get full name
        display_attr = self.settings.AUTH_LDAP_USER_DISPLAY_NAME_ATTR
        full_name = None
        if display_attr in attrs and attrs[display_attr]:
            full_name = attrs[display_attr][0] if isinstance(attrs[display_attr], list) else attrs[display_attr]

        # Get groups (memberOf in AD)
        group_attr = self.settings.AUTH_LDAP_GROUP_MEMBER_ATTR
        groups: list[str] = []
        if group_attr in attrs and attrs[group_attr]:
            groups = attrs[group_attr] if isinstance(attrs[group_attr], list) else [attrs[group_attr]]

        # Check userAccountControl for disabled flag (0x2 = ACCOUNTDISABLE)
        is_active = True
        if "userAccountControl" in attrs and attrs["userAccountControl"]:
            try:
                uac = int(attrs["userAccountControl"][0])
                is_active = not (uac & 0x2)
            except (ValueError, TypeError):
                pass

        return LDAPUserProfile(
            login=login,
            email=email,
            full_name=full_name,
            external_id=entry.entry_dn,
            groups=groups,
            is_active=is_active,
        )

    async def authenticate(self, login: str, password: str) -> LDAPAuthResult:
        """
        Authenticate user against LDAP.

        1. Search user DN with service account
        2. Bind with user DN + provided password
        3. Return user profile on success
        """
        if not self.settings.AUTH_LDAP_ENABLED:
            return LDAPAuthResult(success=False, error="LDAP not enabled")

        if not login or not password:
            return LDAPAuthResult(success=False, error="Missing credentials")

        # Get service connection for user lookup
        service_conn = self._get_service_connection()
        if not service_conn:
            return LDAPAuthResult(success=False, error="LDAP service unavailable")

        try:
            # Search for user
            search_base = self.settings.AUTH_LDAP_USER_SEARCH_BASEDN
            user_filter = self._build_user_filter(login)

            service_conn.search(
                search_base=search_base or "",
                search_filter=user_filter,
                search_scope="SUBTREE",
                attributes=[
                    self.settings.AUTH_LDAP_USER_EMAIL_ATTR,
                    self.settings.AUTH_LDAP_USER_DISPLAY_NAME_ATTR,
                    self.settings.AUTH_LDAP_GROUP_MEMBER_ATTR,
                    "userAccountControl",
                ],
            )

            if not service_conn.entries:
                return LDAPAuthResult(success=False, error="User not found")

            user_entry = service_conn.entries[0]
            user_dn = user_entry.entry_dn

            # Try to bind as user with provided password
            try:
                user_conn = Connection(
                    self._get_server(),
                    user=user_dn,
                    password=password,
                    auto_bind=AUTO_BIND_NO_TLS if not self.settings.AUTH_LDAP_USE_TLS else True,
                    receive_timeout=self.settings.AUTH_LDAP_TIMEOUT_SECONDS,
                )
                # Close immediately - bind success means auth success
                user_conn.unbind()
            except LDAPBindError:
                return LDAPAuthResult(success=False, error="Invalid credentials")
            except LDAPException as exc:
                return LDAPAuthResult(success=False, error=f"LDAP bind error: {exc}")

            # Parse profile from entry we already have
            profile = self._parse_user_entry(user_entry, login)
            if not profile:
                return LDAPAuthResult(success=False, error="Failed to parse user profile")

            return LDAPAuthResult(success=True, user=profile)

        except LDAPException as exc:
            logger.warning(f"LDAP authentication error: {exc}")
            return LDAPAuthResult(success=False, error=f"LDAP error: {exc}")
        finally:
            if service_conn:
                service_conn.unbind()

    async def lookup_user(self, login: str) -> LDAPUserProfile | None:
        """
        Lookup user by login (without authentication).
        Used for sync tasks to check user status in AD.
        """
        if not self.settings.AUTH_LDAP_ENABLED:
            return None

        service_conn = self._get_service_connection()
        if not service_conn:
            return None

        try:
            search_base = self.settings.AUTH_LDAP_USER_SEARCH_BASEDN
            user_filter = self._build_user_filter(login)

            service_conn.search(
                search_base=search_base or "",
                search_filter=user_filter,
                search_scope="SUBTREE",
                attributes=[
                    self.settings.AUTH_LDAP_USER_EMAIL_ATTR,
                    self.settings.AUTH_LDAP_USER_DISPLAY_NAME_ATTR,
                    self.settings.AUTH_LDAP_GROUP_MEMBER_ATTR,
                    "userAccountControl",
                ],
            )

            if not service_conn.entries:
                return None

            return self._parse_user_entry(service_conn.entries[0], login)

        except LDAPException as exc:
            logger.warning(f"LDAP lookup error: {exc}")
            return None
        finally:
            if service_conn:
                service_conn.unbind()

    async def health_check(self) -> dict[str, Any]:
        """
        Check LDAP connectivity and service account bind.
        Returns dict with status and details.
        """
        if not self.settings.AUTH_LDAP_ENABLED:
            return {"status": "disabled", "reachable": False, "error": None}

        service_conn = self._get_service_connection()
        if not service_conn:
            return {
                "status": "error",
                "reachable": False,
                "error": "Failed to bind service account",
            }

        try:
            # Try a simple search to verify full functionality
            search_base = self.settings.AUTH_LDAP_USER_SEARCH_BASEDN
            service_conn.search(
                search_base=search_base or "",
                search_filter="(objectClass=*)",
                search_scope="BASE",
                attributes=["dn"],
                size_limit=1,
            )

            return {
                "status": "healthy",
                "reachable": True,
                "error": None,
                "server_uri": self.settings.AUTH_LDAP_SERVER_URI,
            }

        except LDAPException as exc:
            return {
                "status": "error",
                "reachable": True,  # Connection worked but search failed
                "error": str(exc),
                "server_uri": self.settings.AUTH_LDAP_SERVER_URI,
            }
        finally:
            if service_conn:
                service_conn.unbind()
