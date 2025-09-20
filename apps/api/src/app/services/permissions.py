from __future__ import annotations
def is_owner(resource_owner_id: str, requester_id: str) -> bool:
    return str(resource_owner_id) == str(requester_id)
