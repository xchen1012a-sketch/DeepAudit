# -*- coding: utf-8 -*-
"""风险事件 ORM 模型"""

from datetime import datetime
from core.extensions import db


class RiskEvent(db.Model):
    __tablename__ = "risk_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    event_type = db.Column(db.String(64), nullable=False, default="", index=True)
    severity = db.Column(db.String(32), nullable=False, default="MEDIUM", index=True)
    status = db.Column(db.String(32), nullable=False, default="OPEN", index=True)
    source_type = db.Column(db.String(64), nullable=False, default="")
    source_id = db.Column(db.String(128), nullable=False, default="", index=True)
    description = db.Column(db.Text, nullable=False, default="")
    risk_score = db.Column(db.Float, nullable=False, default=0.0)
    assigned_to = db.Column(db.Integer, nullable=True, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, nullable=True)
    resolution_note = db.Column(db.Text, nullable=False, default="")
    meta_json = db.Column(db.Text, nullable=False, default="")  # JSON，避免与 SQLAlchemy metadata 冲突

    def __repr__(self):
        return f"<RiskEvent {self.id} {self.event_type} {self.status}>"

