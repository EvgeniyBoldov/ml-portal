#!/usr/bin/env python3
"""
CLI commands for the ML Portal application.
"""
import argparse
import sys
from typing import Optional
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.security import hash_password
from app.repositories.users_repo import UsersRepo


def create_superuser(login: str, password: str, email: Optional[str] = None) -> None:
    """Create a superuser account."""
    session = next(get_session())
    repo = UsersRepo(session)
    
    try:
        # Check if user already exists
        existing_user = repo.by_login(login)
        if existing_user:
            print(f"❌ Error: User with login '{login}' already exists")
            sys.exit(1)
        
        # Create superuser
        password_hash = hash_password(password)
        user = repo.create_user(
            login=login,
            password_hash=password_hash,
            role="admin",
            email=email,
            is_active=True
        )
        
        print(f"✅ Superuser created successfully!")
        print(f"   Login: {user.login}")
        print(f"   Role: {user.role}")
        print(f"   Email: {user.email or 'Not set'}")
        print(f"   ID: {user.id}")
        
    except Exception as e:
        print(f"❌ Error creating superuser: {e}")
        sys.exit(1)
    finally:
        session.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="ML Portal CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create superuser command
    create_superuser_parser = subparsers.add_parser(
        "create-superuser",
        help="Create a superuser account"
    )
    create_superuser_parser.add_argument(
        "--login",
        required=True,
        help="Login username"
    )
    create_superuser_parser.add_argument(
        "--password",
        required=True,
        help="Password (min 12 characters)"
    )
    create_superuser_parser.add_argument(
        "--email",
        help="Email address (optional)"
    )
    
    args = parser.parse_args()
    
    if args.command == "create-superuser":
        if len(args.password) < 12:
            print("❌ Error: Password must be at least 12 characters long")
            sys.exit(1)
        
        create_superuser(
            login=args.login,
            password=args.password,
            email=args.email
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
