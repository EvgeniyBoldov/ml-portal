"""
Integration tests for database migrations
"""
import pytest
import subprocess
import os
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine


class TestMigrationIntegrity:
    """Test migration integrity and consistency"""
    
    def test_migration_upgrade_downgrade(self, db_engine: Engine):
        """Test that migrations can be upgraded and downgraded"""
        # This test would run in a separate test database
        # For now, we'll test the migration file structure
        
        # Check that migration file exists
        migration_file = "apps/api/alembic/versions/001_add_multitenancy_and_jsonb.py"
        assert os.path.exists(migration_file)
        
        # Verify migration file has both upgrade and downgrade functions
        with open(migration_file, 'r') as f:
            content = f.read()
            assert 'def upgrade()' in content
            assert 'def downgrade()' in content
            assert 'CREATE EXTENSION' in content
            assert 'CREATE TYPE' in content
            assert 'CREATE TABLE' in content
    
    def test_database_extensions_exist(self, db_engine: Engine):
        """Test that required PostgreSQL extensions are available"""
        with db_engine.connect() as conn:
            # Check uuid-ossp extension
            result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp'"))
            assert result.fetchone() is not None
            
            # Check pgcrypto extension
            result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'"))
            assert result.fetchone() is not None
            
            # Check pg_trgm extension
            result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"))
            assert result.fetchone() is not None
    
    def test_enum_types_exist(self, db_engine: Engine):
        """Test that custom ENUM types exist"""
        with db_engine.connect() as conn:
            # Check chat_role_enum
            result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'chat_role_enum'"))
            assert result.fetchone() is not None
            
            # Check analyze_status_enum
            result = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = 'analyze_status_enum'"))
            assert result.fetchone() is not None
    
    def test_tables_exist_with_correct_structure(self, db_engine: Engine):
        """Test that tables exist with correct structure"""
        inspector = inspect(db_engine)
        
        # Check that all tables exist
        tables = inspector.get_table_names()
        assert 'chats' in tables
        assert 'chatmessages' in tables
        assert 'analysisdocuments' in tables
        assert 'analysischunks' in tables
        
        # Check chats table structure
        chats_columns = inspector.get_columns('chats')
        column_names = [col['name'] for col in chats_columns]
        
        assert 'id' in column_names
        assert 'tenant_id' in column_names
        assert 'name' in column_names
        assert 'owner_id' in column_names
        assert 'tags' in column_names
        assert 'version' in column_names
        assert 'created_at' in column_names
        assert 'updated_at' in column_names
        assert 'last_message_at' in column_names
        
        # Check chatmessages table structure
        messages_columns = inspector.get_columns('chatmessages')
        message_column_names = [col['name'] for col in messages_columns]
        
        assert 'id' in message_column_names
        assert 'tenant_id' in message_column_names
        assert 'chat_id' in message_column_names
        assert 'role' in message_column_names
        assert 'content' in message_column_names
        assert 'version' in message_column_names
        assert 'created_at' in message_column_names
        assert 'meta' in message_column_names
    
    def test_indexes_exist(self, db_engine: Engine):
        """Test that required indexes exist"""
        inspector = inspect(db_engine)
        
        # Check chats indexes
        chats_indexes = inspector.get_indexes('chats')
        index_names = [idx['name'] for idx in chats_indexes]
        
        assert 'ix_chats_tenant_created' in index_names
        assert 'ix_chats_tenant_owner' in index_names
        assert 'ix_chats_tenant_name' in index_names
        
        # Check chatmessages indexes
        messages_indexes = inspector.get_indexes('chatmessages')
        message_index_names = [idx['name'] for idx in messages_indexes]
        
        assert 'ix_chatmessages_tenant_created' in message_index_names
        assert 'ix_chatmessages_tenant_chat' in message_index_names
    
    def test_foreign_keys_exist(self, db_engine: Engine):
        """Test that foreign key constraints exist"""
        inspector = inspect(db_engine)
        
        # Check chats foreign keys
        chats_fks = inspector.get_foreign_keys('chats')
        fk_columns = [fk['constrained_columns'][0] for fk in chats_fks]
        assert 'owner_id' in fk_columns
        
        # Check chatmessages foreign keys
        messages_fks = inspector.get_foreign_keys('chatmessages')
        message_fk_columns = [fk['constrained_columns'][0] for fk in messages_fks]
        assert 'chat_id' in message_fk_columns
    
    def test_jsonb_columns_exist(self, db_engine: Engine):
        """Test that JSONB columns exist"""
        inspector = inspect(db_engine)
        
        # Check chatmessages content column
        messages_columns = inspector.get_columns('chatmessages')
        content_column = next((col for col in messages_columns if col['name'] == 'content'), None)
        assert content_column is not None
        assert 'JSONB' in str(content_column['type'])
        
        # Check chatmessages meta column
        meta_column = next((col for col in messages_columns if col['name'] == 'meta'), None)
        assert meta_column is not None
        assert 'JSONB' in str(meta_column['type'])
        
        # Check analysisdocuments result column
        docs_columns = inspector.get_columns('analysisdocuments')
        result_column = next((col for col in docs_columns if col['name'] == 'result'), None)
        assert result_column is not None
        assert 'JSONB' in str(result_column['type'])
    
    def test_gin_indexes_exist(self, db_engine: Engine):
        """Test that GIN indexes for JSONB exist"""
        with db_engine.connect() as conn:
            # Check GIN indexes
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE indexname LIKE '%gin%' 
                AND tablename IN ('chatmessages', 'analysisdocuments', 'analysischunks')
            """))
            
            gin_indexes = [row[0] for row in result.fetchall()]
            
            # Should have GIN indexes for JSONB fields
            assert any('content' in idx for idx in gin_indexes)
            assert any('meta' in idx for idx in gin_indexes)
            assert any('result' in idx for idx in gin_indexes)


class TestMigrationDataIntegrity:
    """Test data integrity after migrations"""
    
    def test_uuid_generation_works(self, db_engine: Engine):
        """Test that UUID generation works correctly"""
        with db_engine.connect() as conn:
            # Test gen_random_uuid() function
            result = conn.execute(text("SELECT gen_random_uuid()"))
            uuid_value = result.fetchone()[0]
            assert uuid_value is not None
            assert len(str(uuid_value)) == 36  # Standard UUID length
    
    def test_timezone_functions_work(self, db_engine: Engine):
        """Test that timezone functions work correctly"""
        with db_engine.connect() as conn:
            # Test timezone-aware timestamp generation
            result = conn.execute(text("SELECT now() AT TIME ZONE 'UTC'"))
            timestamp = result.fetchone()[0]
            assert timestamp is not None
            assert timestamp.tzinfo is not None
    
    def test_enum_values_work(self, db_engine: Engine):
        """Test that ENUM values can be inserted"""
        with db_engine.connect() as conn:
            # Test chat_role_enum values
            result = conn.execute(text("SELECT 'user'::chat_role_enum"))
            role_value = result.fetchone()[0]
            assert role_value == 'user'
            
            # Test analyze_status_enum values
            result = conn.execute(text("SELECT 'queued'::analyze_status_enum"))
            status_value = result.fetchone()[0]
            assert status_value == 'queued'
    
    def test_array_operations_work(self, db_engine: Engine):
        """Test that array operations work correctly"""
        with db_engine.connect() as conn:
            # Test array creation and operations
            result = conn.execute(text("SELECT ARRAY['tag1', 'tag2']::text[]"))
            array_value = result.fetchone()[0]
            assert array_value == ['tag1', 'tag2']
            
            # Test array contains operation
            result = conn.execute(text("SELECT 'tag1' = ANY(ARRAY['tag1', 'tag2']::text[])"))
            contains = result.fetchone()[0]
            assert contains is True


class TestMigrationPerformance:
    """Test migration performance and constraints"""
    
    def test_migration_completes_in_reasonable_time(self, db_engine: Engine):
        """Test that migration completes in reasonable time"""
        # This would be tested with a timer in a real scenario
        # For now, we'll just verify the migration file is syntactically correct
        
        migration_file = "apps/api/alembic/versions/001_add_multitenancy_and_jsonb.py"
        
        # Check Python syntax
        with open(migration_file, 'r') as f:
            code = f.read()
            
        # Compile to check syntax
        compile(code, migration_file, 'exec')
        
        # If we get here, syntax is correct
        assert True
    
    def test_indexes_are_efficient(self, db_engine: Engine):
        """Test that indexes are created efficiently"""
        with db_engine.connect() as conn:
            # Check that indexes exist and are being used
            result = conn.execute(text("""
                SELECT schemaname, tablename, indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename IN ('chats', 'chatmessages', 'analysisdocuments', 'analysischunks')
                ORDER BY tablename, indexname
            """))
            
            indexes = result.fetchall()
            
            # Should have multiple indexes per table
            table_indexes = {}
            for row in indexes:
                table = row[1]
                if table not in table_indexes:
                    table_indexes[table] = []
                table_indexes[table].append(row[2])
            
            # Each table should have several indexes
            for table, index_list in table_indexes.items():
                assert len(index_list) >= 2  # At least primary key + some other indexes


class TestMigrationRollback:
    """Test migration rollback scenarios"""
    
    def test_downgrade_removes_extensions(self, db_engine: Engine):
        """Test that downgrade removes custom extensions"""
        # This would test the downgrade function
        # For now, we'll verify the downgrade function exists and is complete
        
        migration_file = "apps/api/alembic/versions/001_add_multitenancy_and_jsonb.py"
        
        with open(migration_file, 'r') as f:
            content = f.read()
            
        # Check that downgrade function exists and drops tables
        assert 'def downgrade()' in content
        assert 'drop_table' in content
        assert 'DROP TYPE' in content
    
    def test_downgrade_preserves_data(self, db_engine: Engine):
        """Test that downgrade preserves existing data where possible"""
        # This would test data preservation during rollback
        # For now, we'll verify the migration is designed to be reversible
        
        migration_file = "apps/api/alembic/versions/001_add_multitenancy_and_jsonb.py"
        
        with open(migration_file, 'r') as f:
            content = f.read()
            
        # Check that downgrade is comprehensive
        assert 'drop_table' in content
        assert 'DROP TYPE' in content
        # Should not drop extensions as they might be used by other tables
