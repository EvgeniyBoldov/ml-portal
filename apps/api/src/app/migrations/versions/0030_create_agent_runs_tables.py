"""Create agent_runs and agent_run_steps tables, add enable_logging to agents

Revision ID: 0030
Revises: 0029
Create Date: 2024-12-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0030'
down_revision = '0029_update_rag_agent_prompt'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add enable_logging to agents table
    op.add_column(
        'agents',
        sa.Column('enable_logging', sa.Boolean(), nullable=False, server_default='true')
    )
    
    # Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chat_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chatmessages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_slug', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='running'),
        sa.Column('total_steps', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tool_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for agent_runs
    op.create_index('ix_agent_runs_tenant_id', 'agent_runs', ['tenant_id'])
    op.create_index('ix_agent_runs_user_id', 'agent_runs', ['user_id'])
    op.create_index('ix_agent_runs_chat_id', 'agent_runs', ['chat_id'])
    op.create_index('ix_agent_runs_agent_slug', 'agent_runs', ['agent_slug'])
    op.create_index('ix_agent_runs_status', 'agent_runs', ['status'])
    op.create_index('ix_agent_runs_started_at', 'agent_runs', ['started_at'])
    
    # Create agent_run_steps table
    op.create_table(
        'agent_run_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('step_type', sa.String(50), nullable=False),  # llm_request, tool_call, tool_result, final_response
        sa.Column('data', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create indexes for agent_run_steps
    op.create_index('ix_agent_run_steps_run_id', 'agent_run_steps', ['run_id'])
    op.create_index('ix_agent_run_steps_step_type', 'agent_run_steps', ['step_type'])


def downgrade() -> None:
    op.drop_table('agent_run_steps')
    op.drop_table('agent_runs')
    op.drop_column('agents', 'enable_logging')
