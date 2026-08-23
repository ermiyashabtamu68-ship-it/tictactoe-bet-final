"""
services/audit_service.py

One function, used everywhere an admin does something sensitive.
Writing an audit log row is never optional for these actions —
that's the whole point of "full audit logs" from the spec.
"""

import uuid
from sqlalchemy.orm import Session

from app.models.models import AuditLog


def log_admin_action(
    db: Session,
    admin_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    metadata: dict = None,
):
    entry = AuditLog(
        actor_type="admin",
        actor_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        audit_metadata=metadata or {},
    )
    db.add(entry)
    # Deliberately NOT committing here — the caller commits as part
    # of the same transaction as the actual change, so the action
    # and its audit record either both succeed or both fail together.
