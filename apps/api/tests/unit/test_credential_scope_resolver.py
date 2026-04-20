from app.services.credential_scope_resolver import CredentialScopeResolver, OperationFlags


def test_explicit_user_only_wins_over_risk():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(
            credential_scope="user_only",
            risk_level="high",
            side_effects="destructive",
            requires_confirmation=True,
        )
    )
    assert strategy == "USER_ONLY"


def test_explicit_platform_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(OperationFlags(credential_scope="platform_only"))
    assert strategy == "PLATFORM_ONLY"


def test_explicit_any_non_user():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(OperationFlags(credential_scope="any_non_user"))
    assert strategy == "TENANT_THEN_PLATFORM"


def test_any_safe_prefers_platform_first():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="any", side_effects="none", risk_level="low")
    )
    assert strategy == "PLATFORM_FIRST"


def test_any_write_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="any", side_effects="write", risk_level="low")
    )
    assert strategy == "ANY"


def test_any_high_risk_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="any", side_effects="none", risk_level="high")
    )
    assert strategy == "ANY"


def test_any_requires_confirmation_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="any", requires_confirmation=True)
    )
    assert strategy == "ANY"
