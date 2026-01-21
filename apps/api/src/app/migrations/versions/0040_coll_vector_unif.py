"""Collection vector unification - remove type, add search_modes and vector fields

Revision ID: 0040_collection_vector_unification
Revises: 0039_agent_collections
Create Date: 2026-01-21

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0040_coll_vector_unif'
down_revision: Union[str, None] = '0039_agent_collections'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate collections to new unified architecture:
    - Remove 'type' field (SQL/VECTOR/HYBRID distinction)
    - Add vector_config (JSONB) for vector search configuration
    - Add qdrant_collection_name for vector storage
    - Add vectorization statistics fields
    - Migrate existing fields schema from 'searchable'+'search_mode' to 'search_modes' array
    """
    
    # Add new columns for vector support
    op.add_column(
        'collections',
        sa.Column('vector_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'collections',
        sa.Column('qdrant_collection_name', sa.String(length=200), nullable=True)
    )
    
    # Add vectorization statistics
    op.add_column(
        'collections',
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'collections',
        sa.Column('vectorized_rows', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'collections',
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'collections',
        sa.Column('failed_rows', sa.Integer(), nullable=False, server_default='0')
    )
    
    # Migrate existing fields schema: convert 'searchable' + 'search_mode' to 'search_modes' array
    # This is done via raw SQL to handle JSONB manipulation
    op.execute("""
        UPDATE collections
        SET fields = (
            SELECT jsonb_agg(
                CASE 
                    WHEN (field->>'searchable')::boolean = true THEN
                        field - 'searchable' - 'search_mode' || 
                        jsonb_build_object(
                            'search_modes', 
                            jsonb_build_array(
                                COALESCE(field->>'search_mode', 'exact')
                            )
                        )
                    ELSE
                        field - 'searchable' - 'search_mode' || 
                        jsonb_build_object('search_modes', jsonb_build_array('exact'))
                END
            )
            FROM jsonb_array_elements(fields) AS field
        )
        WHERE fields IS NOT NULL
    """)
    
    # Drop the 'type' column as it's no longer needed
    # Type is now determined by presence of 'vector' in any field's search_modes
    op.drop_column('collections', 'type')


def downgrade() -> None:
    """
    Revert to old schema with type field
    """
    
    # Re-add type column
    op.add_column(
        'collections',
        sa.Column('type', sa.String(length=20), nullable=False, server_default='sql')
    )
    
    # Migrate fields back: convert 'search_modes' array to 'searchable' + 'search_mode'
    op.execute("""
        UPDATE collections
        SET fields = (
            SELECT jsonb_agg(
                CASE 
                    WHEN jsonb_array_length(field->'search_modes') > 0 THEN
                        field - 'search_modes' || 
                        jsonb_build_object(
                            'searchable', true,
                            'search_mode', field->'search_modes'->0
                        )
                    ELSE
                        field - 'search_modes' || 
                        jsonb_build_object('searchable', false)
                END
            )
            FROM jsonb_array_elements(fields) AS field
        )
        WHERE fields IS NOT NULL
    """)
    
    # Set type based on vector_config presence
    op.execute("""
        UPDATE collections
        SET type = CASE 
            WHEN vector_config IS NOT NULL THEN 'hybrid'
            ELSE 'sql'
        END
    """)
    
    # Drop new columns
    op.drop_column('collections', 'failed_rows')
    op.drop_column('collections', 'total_chunks')
    op.drop_column('collections', 'vectorized_rows')
    op.drop_column('collections', 'total_rows')
    op.drop_column('collections', 'qdrant_collection_name')
    op.drop_column('collections', 'vector_config')
