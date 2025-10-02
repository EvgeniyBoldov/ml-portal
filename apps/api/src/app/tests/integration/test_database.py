"""
Интеграционные тесты для работы с базой данных.
Использует реальную PostgreSQL для проверки CRUD операций, транзакций и конкурентности.
"""
import pytest
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.user import Users
from app.models.chat import Chats, ChatMessages
from app.models.rag import RAGDocument, RAGChunk
from app.repositories.users_repo import UsersRepository
from app.repositories.chats_repo import ChatsRepository
from app.services.users_service import UsersService
from app.services.chats_service import ChatsService


@pytest.mark.integration
class TestDatabaseIntegration:
    """Интеграционные тесты для работы с БД."""

    @pytest.mark.asyncio
    async def test_user_crud_operations(self, db_session: AsyncSession, test_tenant_id: str):
        """Тест полного цикла CRUD операций с пользователями."""
        users_repo = UsersRepository(db_session, test_tenant_id)
        
        user_data = {
            "login": "crud_test",
            "email": "crud_test@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        try:
            # CREATE
            created_user = users_repo.create(user_data)
            await db_session.commit()
            await db_session.refresh(created_user)
            
            assert created_user is not None
            assert created_user.email == user_data["email"]
            assert created_user.login == user_data["login"]
            assert created_user.is_active is True

            # READ
            retrieved_user = users_repo.get_by_id(created_user.id)
            assert retrieved_user is not None
            assert retrieved_user.email == user_data["email"]

            # UPDATE
            updated_data = {"login": "updated_crud_user", "is_active": False}
            updated_user = users_repo.update(created_user, updated_data)
            await db_session.commit()
            
            assert updated_user.login == "updated_crud_user"
            assert updated_user.is_active is False

            # DELETE
            users_repo.delete(updated_user)
            await db_session.commit()
            
            # Verify deletion
            deleted_user = users_repo.get_by_id(created_user.id)
            assert deleted_user is None

        except Exception as e:
            await db_session.rollback()
            raise e

    @pytest.mark.asyncio
    async def test_user_service_with_database(self, db_session: AsyncSession, test_tenant_id: str):
        """Тест сервиса пользователей с реальной БД."""
        users_service = UsersService(db_session)
        
        user_data = {
            "email": "service_test@example.com",
            "login": "service_test",
            "password": "testpassword123"
        }

        try:
            # Create user through service
            created_user = users_service.create_user(user_data)
            await db_session.commit()
            await db_session.refresh(created_user)
            
            assert created_user is not None
            assert created_user.email == user_data["email"]
            assert created_user.login == user_data["login"]

            # Get user by email
            retrieved_user = users_service.get_user_by_email(user_data["email"])
            assert retrieved_user is not None
            assert retrieved_user.email == user_data["email"]

            # Update user
            update_data = {"username": "updated_service_user"}
            updated_user = users_service.update_user(created_user.id, update_data)
            await db_session.commit()
            
            assert updated_user.username == "updated_service_user"

        except Exception as e:
            await db_session.rollback()
            raise e
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    delete(Users).where(Users.email == user_data["email"])
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, db_session: AsyncSession, test_tenant_id: str):
        """Тест отката транзакции при ошибке."""
        users_repo = UsersRepository(db_session, test_tenant_id)
        
        user_data = {
            "email": "transaction_test@example.com",
            "login": "transaction_test",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        try:
            # Start transaction
            async with db_session.begin():
                # Create user
                user = users_repo.create(user_data)
                await db_session.flush()
                
                # Simulate error - this should cause rollback
                raise Exception("Simulated error")

        except Exception:
            # Assert - User should not exist due to rollback
            result = await db_session.execute(
                select(Users).where(Users.email == user_data["email"])
            )
            user = result.scalar_one_or_none()
            assert user is None

    @pytest.mark.asyncio
    async def test_concurrent_user_creation(self, db_session: AsyncSession, test_tenant_id: str):
        """Тест создания пользователей в конкурентном режиме."""
        users_repo = UsersRepository(db_session, test_tenant_id)
        
        user_data_list = [
            {
                "email": f"concurrent_test_{i}@example.com",
                "login": f"concurrent_test_{i}",
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                "is_active": True,
                "role": "reader"
            }
            for i in range(5)
        ]

        try:
            # Create users concurrently
            tasks = []
            for user_data in user_data_list:
                task = asyncio.create_task(
                    self._create_user_async(db_session, users_repo, user_data)
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # Assert - All users should be created successfully
            assert len(results) == 5
            for result in results:
                assert result is not None

            # Verify all users exist in database
            for user_data in user_data_list:
                result = await db_session.execute(
                    select(Users).where(Users.email == user_data["email"])
                )
                user = result.scalar_one_or_none()
                assert user is not None

        finally:
            # Cleanup
            for user_data in user_data_list:
                try:
                    await db_session.execute(
                        delete(Users).where(Users.email == user_data["email"])
                    )
                except:
                    pass
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_chat_operations(self, db_session: AsyncSession, test_user: Users):
        """Тест операций с чатами."""
        chats_repo = ChatsRepository(db_session, test_user.tenant_id)
        
        chat_data = {
            "name": "Integration Test Chat",
            "owner_id": test_user.id,
            "tenant_id": test_user.tenant_id
        }

        try:
            # Create chat
            created_chat = chats_repo.create(chat_data)
            await db_session.commit()
            await db_session.refresh(created_chat)
            
            assert created_chat is not None
            assert created_chat.name == chat_data["name"]
            assert created_chat.owner_id == test_user.id

            # Add message to chat
            message_data = {
                "chat_id": created_chat.id,
                "user_id": test_user.id,
                "content": "Hello, this is a test message!",
                "role": "user"
            }
            
            message = ChatMessages(**message_data)
            db_session.add(message)
            await db_session.commit()
            await db_session.refresh(message)
            
            assert message is not None
            assert message.content == message_data["content"]
            assert message.chat_id == created_chat.id

            # Get chat with messages
            chat_with_messages = chats_repo.get_chat_with_messages(created_chat.id)
            assert chat_with_messages is not None
            assert len(chat_with_messages.messages) == 1
            assert chat_with_messages.messages[0].content == message_data["content"]

        except Exception as e:
            await db_session.rollback()
            raise e
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    delete(ChatMessages).where(ChatMessages.chat_id == created_chat.id)
                )
                await db_session.execute(
                    delete(Chats).where(Chats.id == created_chat.id)
                )
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_rag_document_operations(self, db_session: AsyncSession, test_user: Users):
        """Тест операций с RAG документами."""
        from app.repositories.rag_repo import RAGDocumentsRepository
        
        rag_repo = RAGDocumentsRepository(db_session, test_user.tenant_id)
        
        document_data = {
            "filename": "test_document.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "status": "uploaded",
            "user_id": test_user.id
        }

        try:
            # Create RAG document
            created_doc = rag_repo.create(document_data)
            await db_session.commit()
            await db_session.refresh(created_doc)
            
            assert created_doc is not None
            assert created_doc.filename == document_data["filename"]
            assert created_doc.status == document_data["status"]

            # Create RAG chunk
            chunk_data = {
                "document_id": created_doc.id,
                "content": "This is a test chunk content.",
                "chunk_index": 0,
                "metadata": {"page": 1, "section": "introduction"}
            }
            
            chunk = RAGChunk(**chunk_data)
            db_session.add(chunk)
            await db_session.commit()
            await db_session.refresh(chunk)
            
            assert chunk is not None
            assert chunk.content == chunk_data["content"]
            assert chunk.document_id == created_doc.id

            # Update document status
            updated_doc = rag_repo.update(created_doc, {"status": "processed"})
            await db_session.commit()
            
            assert updated_doc.status == "processed"

        except Exception as e:
            await db_session.rollback()
            raise e
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    delete(RAGChunk).where(RAGChunk.document_id == created_doc.id)
                )
                await db_session.execute(
                    delete(RAGDocument).where(RAGDocument.id == created_doc.id)
                )
                await db_session.commit()
            except:
                pass

    async def _create_user_async(self, db_session: AsyncSession, users_repo: UsersRepository, user_data: dict):
        """Вспомогательный метод для создания пользователя."""
        user = users_repo.create(user_data)
        await db_session.commit()
        await db_session.refresh(user)
        return user
