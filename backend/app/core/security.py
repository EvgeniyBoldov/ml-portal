import hashlib

def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def verify_password(raw: str, password_hash: str) -> bool:
    return hash_password(raw) == password_hash
