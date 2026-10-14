import asyncio
import json
import os
from pathlib import Path
from sqlalchemy import select
from app.core.db import get_session_factory
from app.core.security import create_access_token, create_refresh_token
from app.models.user import Users
from app.models.tenant import UserTenants, Tenants


async def main():
    async with get_session_factory()() as session:
        user = (await session.execute(select(Users).join(UserTenants, UserTenants.user_id == Users.id)
            .join(Tenants, Tenants.id == UserTenants.tenant_id)
            .where(Users.is_active.is_(True), Users.lifecycle_status != "deprecated", Tenants.is_active.is_(True))
            .limit(1))).scalar_one()
        ids = list((await session.scalars(select(UserTenants.tenant_id).where(UserTenants.user_id == user.id))).all())
        target = Path("/app/tests/.profile-preview-auth.json")
        with open(target, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as out:
            json.dump({"access_token": create_access_token(str(user.id), user.email or "", user.role, [str(x) for x in ids], []),
                       "refresh_token": create_refresh_token(str(user.id))}, out)
        directory = target.parent.stat()
        os.chown(target, directory.st_uid, directory.st_gid)
        print("Temporary browser credentials prepared; secrets omitted")


asyncio.run(main())
