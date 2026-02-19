# -*- coding: utf-8 -*-
"""审计日志 ORM 模型"""

from datetime import datetime
from core.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    actor_user_id = db.Column(db.Integer, nullable=True, index=True)
    actor_name = db.Column(db.String(128), nullable=False, default="")
    action = db.Column(db.String(64), nullable=False, default="", index=True)
    target_type = db.Column(db.String(64), nullable=False, default="", index=True)
    target_id = db.Column(db.String(128), nullable=False, default="", index=True)
    client_ip = db.Column(db.String(64), nullable=False, default="")
    user_agent = db.Column(db.String(512), nullable=False, default="")
    request_id = db.Column(db.String(64), nullable=False, default="", index=True)
    session_id = db.Column(db.String(128), nullable=False, default="")
    snapshot_before = db.Column(db.Text, nullable=False, default="")  # JSON
    snapshot_after = db.Column(db.Text, nullable=False, default="")   # JSON
    trace_id = db.Column(db.String(64), nullable=False, default="")
    change_reason_code = db.Column(db.String(64), nullable=False, default="")
    detail = db.Column(db.Text, nullable=False, default="")

    def __repr__(self):
        return f"<AuditLog {self.id} {self.action} by {self.actor_name}>"


