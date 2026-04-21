from app.services.credential_scope_resolver import CredentialScopeResolver, OperationFlags


def test_explicit_user_wins_over_risk():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(
            credential_scope="user",
            risk_level="destructive",
            side_effects=True,
            requires_confirmation=True,
        )
    )
    assert strategy == "USER_ONLY"


def test_explicit_platform():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(OperationFlags(credential_scope="platform"))
    assert strategy == "PLATFORM_ONLY"


def test_auto_safe_prefers_platform_first():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="auto", side_effects=False, risk_level="safe")
    )
    assert strategy == "PLATFORM_FIRST"


def test_auto_write_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="auto", side_effects=False, risk_level="write")
    )
    assert strategy == "ANY"


def test_auto_side_effects_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="auto", side_effects=True, risk_level="safe")
    )
    assert strategy == "ANY"


def test_auto_requires_confirmation_is_any():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve_strategy(
        OperationFlags(credential_scope="auto", requires_confirmation=True)
    )
    assert strategy == "ANY"
