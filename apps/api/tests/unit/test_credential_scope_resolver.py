from app.services.credential_scope_resolver import CredentialScopeResolver, CredentialStrategy, OperationFlags


def test_risky_operation_resolves_user_only():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(OperationFlags(is_risky=True))
    assert strategy == CredentialStrategy.USER_ONLY


def test_safe_operation_resolves_user_first_cascade():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(OperationFlags(is_risky=False))
    assert strategy == CredentialStrategy.USER_FIRST


def test_flags_default_to_safe_user_first():
    resolver = CredentialScopeResolver()
    strategy = resolver.resolve(OperationFlags())
    assert strategy == CredentialStrategy.USER_FIRST
