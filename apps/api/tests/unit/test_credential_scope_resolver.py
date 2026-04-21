from app.services.credential_scope_resolver import CredentialScopeResolver, CredentialStrategy, OperationFlags


def test_scope_platform_always_platform_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(
            credential_scope="platform",
            risk_level="destructive",
            side_effects=True,
            requires_confirmation=True,
        )
    )
    assert strategy == CredentialStrategy.PLATFORM_ONLY


def test_scope_user_always_user_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(
            credential_scope="user",
            risk_level="safe",
            side_effects=False,
        )
    )
    assert strategy == CredentialStrategy.USER_ONLY


def test_scope_auto_safe_no_side_effects_platform_first():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(credential_scope="auto", side_effects=False, risk_level="safe")
    )
    assert strategy == CredentialStrategy.PLATFORM_FIRST


def test_scope_auto_safe_with_side_effects_user_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(credential_scope="auto", side_effects=True, risk_level="safe")
    )
    assert strategy == CredentialStrategy.USER_ONLY


def test_scope_auto_write_user_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(credential_scope="auto", side_effects=False, risk_level="write")
    )
    assert strategy == CredentialStrategy.USER_ONLY


def test_scope_auto_destructive_user_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(
        OperationFlags(credential_scope="auto", side_effects=False, risk_level="destructive")
    )
    assert strategy == CredentialStrategy.USER_ONLY
