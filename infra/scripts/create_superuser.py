#!/usr/bin/env python3
"""
Script to create a superuser account.
Usage: python scripts/create_superuser.py --login admin --password 'secure_password123'
"""
import sys
import os
import argparse

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.core.db import get_async_session
from app.core.security import hash_password
from app.repositories.factory import AsyncRepositoryFactory
import asyncio


async def create_superuser(login: str, password: str, email: str = None):
    """Create a superuser account."""
    async for session in get_async_session():
        # Use default tenant for superuser creation
        from uuid import uuid4
        default_tenant_id = uuid4()
        repo_factory = AsyncRepositoryFactory(session, default_tenant_id)
        users_repo = repo_factory.get_users_repository()
        
        try:
            # Check if user already exists
            existing_user = await users_repo.get_by_login(login)
            if existing_user:
                print(f"❌ Error: User with login '{login}' already exists")
                return False
            
            # Validate password
            if len(password) < 12:
                print("❌ Error: Password must be at least 12 characters long")
                return False
            
            # Create superuser
            password_hash = hash_password(password)
            user = await users_repo.create(
                login=login,
                password_hash=password_hash,
                role="admin",
                email=email,
                is_active=True
            )
            
            # Add user to tenant
            await users_repo.add_to_tenant(user.id, default_tenant_id, is_default=True)
            
            # Commit the transaction
            await session.commit()
            
            print(f"✅ Superuser created successfully!")
            print(f"   Login: {user.login}")
            print(f"   Role: {user.role}")
            print(f"   Email: {user.email or 'Not set'}")
            print(f"   ID: {user.id}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating superuser: {e}")
            return False
        finally:
            await session.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Create a superuser account")
    parser.add_argument("--login", required=True, help="Login username")
    parser.add_argument("--password", required=True, help="Password (min 12 characters)")
    parser.add_argument("--email", help="Email address (optional)")
    
    args = parser.parse_args()
    
    success = asyncio.run(create_superuser(
        login=args.login,
        password=args.password,
        email=args.email
    ))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
