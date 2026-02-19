"""Add AuditLog and RiskEvent models

Revision ID: 001_audit_risk
Revises: 
Create Date: 2026-02-18 16:07:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_audit_risk'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 检查 audit_log 表是否存在，如果不存在则创建
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'audit_log' not in existing_tables:
        op.create_table('audit_log',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('actor_user_id', sa.Integer(), nullable=True),
            sa.Column('actor_name', sa.String(length=128), nullable=False),
            sa.Column('action', sa.String(length=64), nullable=False),
            sa.Column('target_type', sa.String(length=64), nullable=False),
            sa.Column('target_id', sa.String(length=128), nullable=False),
            sa.Column('client_ip', sa.String(length=64), nullable=False),
            sa.Column('user_agent', sa.String(length=512), nullable=False),
            sa.Column('request_id', sa.String(length=64), nullable=False),
            sa.Column('session_id', sa.String(length=128), nullable=False),
            sa.Column('snapshot_before', sa.Text(), nullable=False),
            sa.Column('snapshot_after', sa.Text(), nullable=False),
            sa.Column('trace_id', sa.String(length=64), nullable=False),
            sa.Column('change_reason_code', sa.String(length=64), nullable=False),
            sa.Column('detail', sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
        op.create_index(op.f('ix_audit_log_actor_user_id'), 'audit_log', ['actor_user_id'], unique=False)
        op.create_index(op.f('ix_audit_log_created_at'), 'audit_log', ['created_at'], unique=False)
        op.create_index(op.f('ix_audit_log_request_id'), 'audit_log', ['request_id'], unique=False)
        op.create_index(op.f('ix_audit_log_target_id'), 'audit_log', ['target_id'], unique=False)
        op.create_index(op.f('ix_audit_log_target_type'), 'audit_log', ['target_type'], unique=False)
    else:
        # 表已存在，检查并添加缺失字段
        columns = [col['name'] for col in inspector.get_columns('audit_log')]
        
        if 'user_agent' not in columns:
            op.add_column('audit_log', sa.Column('user_agent', sa.String(length=512), nullable=False, server_default=''))
        if 'request_id' not in columns:
            op.add_column('audit_log', sa.Column('request_id', sa.String(length=64), nullable=False, server_default=''))
            op.create_index(op.f('ix_audit_log_request_id'), 'audit_log', ['request_id'], unique=False)
        if 'session_id' not in columns:
            op.add_column('audit_log', sa.Column('session_id', sa.String(length=128), nullable=False, server_default=''))
    
    # 检查 risk_events 表
    if 'risk_events' not in existing_tables:
        op.create_table('risk_events',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('severity', sa.String(length=32), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('source_type', sa.String(length=64), nullable=False),
            sa.Column('source_id', sa.String(length=128), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('risk_score', sa.Float(), nullable=False),
            sa.Column('assigned_to', sa.Integer(), nullable=True),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.Column('resolved_by', sa.Integer(), nullable=True),
            sa.Column('resolution_note', sa.Text(), nullable=False),
            sa.Column('meta_json', sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_risk_events_assigned_to'), 'risk_events', ['assigned_to'], unique=False)
        op.create_index(op.f('ix_risk_events_created_at'), 'risk_events', ['created_at'], unique=False)
        op.create_index(op.f('ix_risk_events_event_type'), 'risk_events', ['event_type'], unique=False)
        op.create_index(op.f('ix_risk_events_severity'), 'risk_events', ['severity'], unique=False)
        op.create_index(op.f('ix_risk_events_source_id'), 'risk_events', ['source_id'], unique=False)
        op.create_index(op.f('ix_risk_events_status'), 'risk_events', ['status'], unique=False)


def downgrade():
    op.drop_table('risk_events')
    op.drop_table('audit_log')


