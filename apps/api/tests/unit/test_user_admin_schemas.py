from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.users import UserCreate, UserUpdate


def test_user_create_accepts_one_tenant_and_optional_email() -> None:
    tenant_id = uuid4()

    payload = UserCreate(
        login="local-user",
        password="a-secure-password",
        email=None,
        tenant_id=tenant_id,
    )

    assert payload.tenant_id == tenant_id
    assert payload.email is None


def test_user_create_rejects_legacy_tenant_ids() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            login="local-user",
            password="a-secure-password",
            tenant_ids=[str(uuid4())],
        )


def test_user_update_distinguishes_omitted_and_cleared_values() -> None:
    omitted = UserUpdate()
    cleared = UserUpdate(tenant_id=None, email=None)

    assert omitted.model_dump(exclude_unset=True) == {}
    assert cleared.model_dump(exclude_unset=True) == {"tenant_id": None, "email": None}
