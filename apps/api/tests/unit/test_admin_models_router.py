"""Unit tests for admin models router (app/api/v1/routers/admin/models.py)."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import ProgrammingError

from app.api.v1.routers.admin import models as models_router
from app.models.model_registry import HealthStatus
from app.schemas.model_registry import (
    HealthCheckRequest,
    ModelCreate,
    ModelProbeRequest,
    ModelProbeResponse,
    ModelStatusEnum,
    ModelTypeEnum,
    ModelUpdate,
)
from app.services.credential_service import CredentialError

MODULE = "app.api.v1.routers.admin.models"
MODEL_ID = uuid4()
INSTANCE_ID = uuid4()


def make_model(**overrides):
    base = dict(
        id=MODEL_ID,
        alias="emb.default",
        name="Default embedding",
        type=ModelTypeEnum.EMBEDDING,
        provider="local",
        connector="local_emb_http",
        provider_model_name="emb-1",
        embedding_dimensions=None,
        max_input_tokens=None,
        vector_normalized=None,
        capabilities_checked_at=None,
        context_window_tokens=16384,
        request_timeout_s=None,
        max_retries=None,
        base_url="http://localhost:9009",
        instance_id=None,
        instance=None,
        extra_config={},
        status=ModelStatusEnum.AVAILABLE,
        enabled=True,
        is_system=False,
        default_for_type=False,
        use_for_long_memory=False,
        model_version="",
        description=None,
        last_health_check_at=None,
        health_status=None,
        health_error=None,
        health_latency_ms=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deleted_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def sql_result(rows):
    return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


class TestSerializeModel:
    def test_serializes_loaded_instance_and_enum_values(self):
        with patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))):
            data = models_router.serialize_model(
                make_model(instance=SimpleNamespace(name="inst-1"))
            )
        assert data["id"] == str(MODEL_ID)
        assert data["instance_name"] == "inst-1"
        assert data["type"] == "embedding"
        assert data["status"] == "available"
        assert data["connector"] == "local_emb_http"
        assert data["base_url"] == "http://localhost:9009"
        assert data["instance_id"] is None

    def test_unloaded_instance_relation_is_not_touched(self):
        with patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded={"instance"}))):
            data = models_router.serialize_model(
                make_model(instance=SimpleNamespace(name="inst-1"))
            )
        assert data["instance_name"] is None

    def test_none_instance_and_plain_string_enums(self):
        with patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))):
            data = models_router.serialize_model(
                make_model(type="embedding", status="maintenance", instance=None)
            )
        assert data["instance_name"] is None
        assert data["type"] == "embedding"
        assert data["status"] == "maintenance"


class TestLoadEmbeddingUsageRows:
    async def test_membership_sql_success(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=sql_result(
                [
                    {
                        "collection_id": "c1",
                        "collection_name": "Docs",
                        "collection_slug": "docs",
                        "tenant_id": "t1",
                        "tenant_name": "Acme",
                        "tenant_active": True,
                        "total_docs": 5,
                        "vectorized_docs": 2,
                    },
                    {
                        "collection_id": "c2",
                        "collection_name": None,
                        "collection_slug": None,
                        "tenant_id": "t2",
                        "tenant_name": None,
                        "tenant_active": False,
                        "total_docs": None,
                        "vectorized_docs": None,
                    },
                ]
            )
        )
        rows = await models_router._load_embedding_usage_rows(session, "emb")
        assert rows == [
            {
                "collection_id": "c1",
                "collection_name": "Docs",
                "collection_slug": "docs",
                "tenant_id": "t1",
                "tenant_name": "Acme",
                "tenant_active": True,
                "total_docs": 5,
                "vectorized_docs": 2,
                "not_vectorized_docs": 3,
            },
            {
                "collection_id": "c2",
                "collection_name": "",
                "collection_slug": "",
                "tenant_id": "t2",
                "tenant_name": "",
                "tenant_active": False,
                "total_docs": 0,
                "vectorized_docs": 0,
                "not_vectorized_docs": 0,
            },
        ]
        assert session.execute.await_count == 1
        assert "document_collection_memberships" in str(session.execute.await_args_list[0].args[0])

    async def test_falls_back_when_membership_table_missing(self):
        session = AsyncMock()
        error = ProgrammingError(
            "stmt", {}, Exception('relation "document_collection_memberships" does not exist')
        )
        session.execute = AsyncMock(
            side_effect=[
                error,
                sql_result(
                    [
                        {
                            "collection_id": "c1",
                            "collection_name": "D",
                            "collection_slug": "d",
                            "tenant_id": "t1",
                            "tenant_name": "T",
                            "tenant_active": True,
                            "total_docs": 1,
                            "vectorized_docs": 1,
                        }
                    ]
                ),
            ]
        )
        rows = await models_router._load_embedding_usage_rows(session, "emb")
        assert rows[0]["not_vectorized_docs"] == 0
        assert session.execute.await_count == 2
        assert "source_docs" in str(session.execute.await_args_list[1].args[0])
        assert session.execute.await_args_list[1].args[1] == {"model_alias": "emb"}

    async def test_unrelated_programming_error_reraises(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=ProgrammingError("stmt", {}, Exception("syntax error")))
        with pytest.raises(ProgrammingError):
            await models_router._load_embedding_usage_rows(session, "emb")


class TestProbeModelInfo:
    async def test_invalid_instance_id_rejected(self):
        with pytest.raises(HTTPException) as err:
            await models_router.probe_model_info(
                ModelProbeRequest(instance_id="not-a-uuid"),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        assert err.value.status_code == 400
        assert "Invalid instance_id" in err.value.detail

    async def test_probe_with_direct_base_url(self):
        with patch(
            f"{MODULE}._probe_manifest",
            AsyncMock(return_value=({"alias": "m1", "version": "v2", "modality": "text-embedding"}, "healthy")),
        ) as probe:
            response = await models_router.probe_model_info(
                ModelProbeRequest(base_url="http://m:1/", provider_model_name="m1"),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        # Production only strips whitespace; the trailing slash is kept as-is.
        probe.assert_awaited_once_with(
            "http://m:1/", connector=None, api_key=None, extra_config=None, provider_model_name="m1"
        )
        assert response == {
            "provider_model_name": "m1",
            "model_version": "v2",
            "model_type": "embedding",
            "health_status": "healthy",
            "raw": {"alias": "m1", "version": "v2", "modality": "text-embedding"},
        }

    @pytest.mark.parametrize(
        "auth_type,payload,expected_key",
        [
            ("api_key", {"api_key": "k1"}, "k1"),
            ("litellm_api_key", {"api_key": "lk"}, "lk"),
            ("token", {"token": "tk"}, "tk"),
            ("basic", {"password": "pw"}, "pw"),
            ("oauth", {"access": "no"}, None),
        ],
    )
    async def test_instance_credential_auth_types(self, auth_type, payload, expected_key):
        creds = MagicMock()
        creds.return_value.resolve_credentials = AsyncMock(
            return_value=SimpleNamespace(payload=payload, auth_type=auth_type)
        )
        repo = MagicMock()
        repo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(url=" http://inst:1 "))
        with patch(f"{MODULE}.CredentialService", creds), patch(f"{MODULE}.ToolInstanceRepository", repo), patch(
            f"{MODULE}._probe_manifest", AsyncMock(return_value=({"alias": "m"}, "healthy"))
        ) as probe:
            await models_router.probe_model_info(
                ModelProbeRequest(instance_id=str(INSTANCE_ID)),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        creds.return_value.resolve_credentials.assert_awaited_once_with(
            instance_id=INSTANCE_ID, strategy="PLATFORM_FIRST"
        )
        probe.assert_awaited_once_with(
            "http://inst:1", connector=None, api_key=expected_key, extra_config=None, provider_model_name=None
        )

    async def test_credential_error_is_swallowed_and_missing_url_rejected(self):
        creds = MagicMock()
        creds.return_value.resolve_credentials = AsyncMock(side_effect=CredentialError("locked"))
        repo = MagicMock()
        repo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(url=None))
        with patch(f"{MODULE}.CredentialService", creds), patch(f"{MODULE}.ToolInstanceRepository", repo), patch(
            f"{MODULE}._probe_manifest", AsyncMock(side_effect=AssertionError)
        ) as probe:
            with pytest.raises(HTTPException) as err:
                await models_router.probe_model_info(
                    ModelProbeRequest(instance_id=str(INSTANCE_ID)),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 400
        assert "base_url or instance_id" in err.value.detail
        probe.assert_not_awaited()

    async def test_instance_url_not_queried_when_base_url_given(self):
        creds = MagicMock()
        creds.return_value.resolve_credentials = AsyncMock(return_value=None)
        repo = MagicMock()
        repo.return_value.get_by_id = AsyncMock()
        with patch(f"{MODULE}.CredentialService", creds), patch(f"{MODULE}.ToolInstanceRepository", repo), patch(
            f"{MODULE}._probe_manifest", AsyncMock(return_value=({"alias": "m"}, "healthy"))
        ):
            await models_router.probe_model_info(
                ModelProbeRequest(base_url="http://direct:2", instance_id=str(INSTANCE_ID)),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        repo.return_value.get_by_id.assert_not_awaited()

    async def test_non_dict_extra_config_is_dropped(self):
        payload = SimpleNamespace(
            model_dump=lambda: {
                "base_url": "http://x:1",
                "extra_config": ["bad"],
                "provider_model_name": "pm",
            }
        )
        with patch(
            f"{MODULE}._probe_manifest", AsyncMock(return_value=({"alias": "m"}, "healthy"))
        ) as probe:
            await models_router.probe_model_info(
                payload, session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        assert probe.await_args.kwargs["extra_config"] is None

    async def test_probe_failure_returns_warning_payload(self):
        with patch(f"{MODULE}._probe_manifest", AsyncMock(side_effect=RuntimeError("down"))):
            response = await models_router.probe_model_info(
                ModelProbeRequest(base_url="http://m:1", provider_model_name="pm"),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        assert isinstance(response, ModelProbeResponse)
        assert response.provider_model_name == "pm"
        assert response.warning is not None
        assert "unavailable" in response.warning.lower()


class TestVerifyModel:
    def _patches(self, service, manifest, health_status):
        return [
            patch(f"{MODULE}.ModelService", MagicMock(return_value=service)),
            patch(f"{MODULE}._resolve_base_url", MagicMock(return_value="http://m:1")),
            patch(f"{MODULE}._resolve_model_api_key", AsyncMock(return_value="key")),
            patch(f"{MODULE}._probe_manifest", AsyncMock(return_value=(manifest, health_status))),
            patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))),
        ]

    async def test_verify_updates_model_from_manifest(self):
        model = make_model()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        service.update_model = AsyncMock(side_effect=[model, model])
        service.update_health_status = AsyncMock()
        manifest = {
            "alias": "new-name",
            "version": "9",
            "modality": "text-embedding",
            "dimensions": 768,
            "normalized": True,
            "important_params": {"x": 1},
            "_health": {"latency_ms": 42},
        }
        with ExitStack() as stack:
            for p in self._patches(service, dict(manifest), "healthy"):
                stack.enter_context(p)
            payload = await models_router.verify_model(
                str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        update_data = service.update_model.await_args_list[0].args[1]
        assert update_data["provider_model_name"] == "new-name"
        assert update_data["model_version"] == "9"
        assert update_data["type"] == "embedding"
        assert update_data["embedding_dimensions"] == 768
        assert update_data["vector_normalized"] is True
        assert isinstance(update_data["capabilities_checked_at"], datetime)
        stored = update_data["extra_config"]["manifest"]
        assert "important_params" not in stored
        assert stored["_health"] == {"latency_ms": 42}
        service.update_health_status.assert_awaited_once_with(
            MODEL_ID, HealthStatus.HEALTHY, latency_ms=42, error=None
        )
        service.update_model.assert_any_await(MODEL_ID, {"status": "available"})
        assert payload["resolved_type_from_manifest"] == "embedding"
        assert payload["manifest"]["alias"] == "new-name"
        assert payload["alias"] == "emb.default"

    async def test_unhealthy_probe_marks_model_unavailable(self):
        model = make_model()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        service.update_model = AsyncMock(side_effect=[model, model])
        service.update_health_status = AsyncMock()
        with ExitStack() as stack:
            for p in self._patches(service, {"alias": "n", "modality": ""}, "unavailable"):
                stack.enter_context(p)
            await models_router.verify_model(
                str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        service.update_health_status.assert_awaited_once_with(
            MODEL_ID, HealthStatus.UNAVAILABLE, latency_ms=None, error="verify_failed"
        )
        service.update_model.assert_any_await(MODEL_ID, {"status": "unavailable"})

    async def test_missing_modality_keeps_existing_type(self):
        model = make_model()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        service.update_model = AsyncMock(side_effect=[model, model])
        service.update_health_status = AsyncMock()
        with ExitStack() as stack:
            for p in self._patches(service, {"alias": "n", "modality": "", "version": "3"}, "healthy"):
                stack.enter_context(p)
            await models_router.verify_model(
                str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        update_data = service.update_model.await_args_list[0].args[1]
        assert "type" not in update_data
        assert update_data["model_version"] == "3"

    async def test_not_found(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.verify_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 404

    async def test_missing_base_url_rejected(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}._resolve_base_url", MagicMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.verify_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 400
        assert "base_url" in err.value.detail

    async def test_failed_update_returns_404(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        service.update_model = AsyncMock(return_value=None)
        with ExitStack() as stack:
            for p in self._patches(service, {"alias": "n"}, "healthy"):
                stack.enter_context(p)
            with pytest.raises(HTTPException) as err:
                await models_router.verify_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 404

    async def test_probe_exception_becomes_400(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}._resolve_base_url", MagicMock(return_value="http://m:1")
        ), patch(f"{MODULE}._resolve_model_api_key", AsyncMock(return_value=None)), patch(
            f"{MODULE}._probe_manifest", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.verify_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 400
        assert "Verify failed: boom" == err.value.detail


class TestGetEmbeddingUsage:
    async def test_not_found(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.get_embedding_usage(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 404

    async def test_non_embedding_model_rejected(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model(type=ModelTypeEnum.LLM_CHAT))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.get_embedding_usage(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 400

    async def test_aggregates_and_sorts_tenants(self):
        model = make_model(type="embedding", alias="emb-1")
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        rows = [
            {
                "collection_id": "c1",
                "collection_name": "C1",
                "collection_slug": "c1",
                "tenant_id": "t2",
                "tenant_name": "Beta",
                "tenant_active": True,
                "total_docs": 5,
                "vectorized_docs": 3,
                "not_vectorized_docs": 2,
            },
            {
                "collection_id": "c2",
                "collection_name": "C2",
                "collection_slug": "c2",
                "tenant_id": "t2",
                "tenant_name": "Beta",
                "tenant_active": True,
                "total_docs": 1,
                "vectorized_docs": 1,
                "not_vectorized_docs": 0,
            },
            {
                "collection_id": "c3",
                "collection_name": "C3",
                "collection_slug": "c3",
                "tenant_id": "t1",
                "tenant_name": "alpha",
                "tenant_active": False,
                "total_docs": 2,
                "vectorized_docs": 0,
                "not_vectorized_docs": 2,
            },
        ]
        session = AsyncMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}._load_embedding_usage_rows", AsyncMock(return_value=rows)
        ) as loader:
            response = await models_router.get_embedding_usage(
                str(MODEL_ID), session=session, user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        loader.assert_awaited_once_with(session, "emb-1")
        assert response["model_id"] == str(MODEL_ID)
        assert response["model_alias"] == "emb-1"
        assert [t["tenant_name"] for t in response["tenants"]] == ["alpha", "Beta"]
        beta = response["tenants"][1]
        assert beta["collection_count"] == 2
        assert beta["total_docs"] == 6
        assert beta["vectorized_docs"] == 4
        assert beta["not_vectorized_docs"] == 2
        assert [c["collection_id"] for c in response["collections"]] == ["c1", "c2", "c3"]
        assert "tenant_active" not in response["collections"][0]

    async def test_loader_failure_becomes_500(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}._load_embedding_usage_rows", AsyncMock(side_effect=RuntimeError("db down"))
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.get_embedding_usage(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 500
        assert "db down" in err.value.detail


class TestListModels:
    async def test_pagination_and_enum_filters(self):
        models = [make_model(alias=f"m{i}", name=f"M{i}") for i in range(25)]
        service = MagicMock()
        service.list_models = AsyncMock(return_value=models)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))
        ):
            response = await models_router.list_models(
                type="embedding",
                status="available",
                enabled_only=True,
                search="m",
                page=2,
                size=10,
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        service.list_models.assert_awaited_once_with(
            type=ModelTypeEnum.EMBEDDING,
            status=ModelStatusEnum.AVAILABLE,
            enabled_only=True,
            search="m",
        )
        assert response["total"] == 25
        assert response["page"] == 2
        assert response["size"] == 10
        assert len(response["items"]) == 10
        assert response["items"][0]["alias"] == "m10"
        assert response["items"][-1]["alias"] == "m19"
        assert response["has_more"] is True

    async def test_last_page_has_no_more(self):
        service = MagicMock()
        service.list_models = AsyncMock(return_value=[make_model() for _ in range(25)])
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))
        ):
            response = await models_router.list_models(
                type=None,
                status=None,
                enabled_only=False,
                search=None,
                page=3,
                size=10,
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        assert len(response["items"]) == 5
        assert response["has_more"] is False
        service.list_models.assert_awaited_once_with(
            type=None, status=None, enabled_only=False, search=None
        )

    async def test_invalid_type_filter_becomes_500(self):
        service = MagicMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.list_models(
                    type="bogus",
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 500
        assert "Failed to list models" in err.value.detail


class TestCreateModel:
    async def test_create_prepares_and_serializes(self):
        model = make_model()
        service = MagicMock()
        service.create_model = AsyncMock(return_value=model)
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(return_value={"prepared": True})
        payload = ModelCreate(
            alias="emb.default",
            name="Default embedding",
            type=ModelTypeEnum.EMBEDDING,
            connector="local_emb_http",
            provider_model_name="emb-1",
            base_url="http://x:1",
        )
        session = AsyncMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ), patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))):
            response = await models_router.create_model(
                payload, session=session, user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        metadata.prepare_write.assert_awaited_once_with(session, payload.model_dump())
        service.create_model.assert_awaited_once_with({"prepared": True})
        assert response["alias"] == "emb.default"

    async def test_value_error_becomes_400(self):
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(side_effect=ValueError("bad payload"))
        with patch(f"{MODULE}.ModelService", MagicMock()), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.create_model(
                    ModelCreate(
                        alias="a.b",
                        name="A",
                        type=ModelTypeEnum.EMBEDDING,
                        connector="local_emb_http",
                        provider_model_name="pm",
                        base_url="http://x:1",
                    ),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 400
        assert err.value.detail == "bad payload"

    async def test_unexpected_error_becomes_500(self):
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(f"{MODULE}.ModelService", MagicMock()), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.create_model(
                    ModelCreate(
                        alias="a.b",
                        name="A",
                        type=ModelTypeEnum.EMBEDDING,
                        connector="local_emb_http",
                        provider_model_name="pm",
                        base_url="http://x:1",
                    ),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 500


class TestGetModel:
    async def test_get_serializes_model(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))
        ):
            response = await models_router.get_model(
                str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        assert response["id"] == str(MODEL_ID)

    async def test_not_found(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.get_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 404

    async def test_invalid_uuid_becomes_500(self):
        service = MagicMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.get_model(
                    "nope", session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 500


class TestUpdateModel:
    async def test_update_prepares_and_serializes(self):
        model = make_model()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        service.update_model = AsyncMock(return_value=make_model(name="New"))
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(return_value={"name": "New"})
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ), patch(f"{MODULE}.inspect", MagicMock(return_value=SimpleNamespace(unloaded=set()))):
            response = await models_router.update_model(
                str(MODEL_ID),
                ModelUpdate(name="New"),
                session=AsyncMock(),
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        metadata.prepare_write.assert_awaited_once()
        service.update_model.assert_awaited_once_with(MODEL_ID, {"name": "New"})
        assert response["name"] == "New"

    async def test_missing_existing_returns_404(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.update_model(
                    str(MODEL_ID),
                    ModelUpdate(name="New"),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 404

    async def test_failed_update_returns_404(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        service.update_model = AsyncMock(return_value=None)
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(return_value={})
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.update_model(
                    str(MODEL_ID),
                    ModelUpdate(name="New"),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 404

    async def test_value_error_becomes_400(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(side_effect=ValueError("nope"))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.update_model(
                    str(MODEL_ID),
                    ModelUpdate(name="New"),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 400

    async def test_unexpected_error_becomes_500(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        service.update_model = AsyncMock(side_effect=RuntimeError("boom"))
        metadata = MagicMock()
        metadata.prepare_write = AsyncMock(return_value={})
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            f"{MODULE}.ModelMetadataService", metadata
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.update_model(
                    str(MODEL_ID),
                    ModelUpdate(name="New"),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 500
        assert "Failed to update model" in err.value.detail


class TestDeleteModel:
    async def test_delete_returns_none_on_success(self):
        service = MagicMock()
        service.delete_model = AsyncMock(return_value=True)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            result = await models_router.delete_model(
                str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        assert result is None
        service.delete_model.assert_awaited_once_with(MODEL_ID)

    async def test_delete_not_found(self):
        service = MagicMock()
        service.delete_model = AsyncMock(return_value=False)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.delete_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 404

    async def test_value_error_becomes_400(self):
        service = MagicMock()
        service.delete_model = AsyncMock(side_effect=ValueError("protected"))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.delete_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 400

    async def test_unexpected_error_becomes_500(self):
        service = MagicMock()
        service.delete_model = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.delete_model(
                    str(MODEL_ID), session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 500
        assert "Failed to delete model" in err.value.detail


class TestHealthCheckAll:
    async def test_summary_across_enabled_models(self):
        m1 = make_model(id=uuid4(), alias="a")
        m2 = make_model(id=uuid4(), alias="b")
        service = MagicMock()
        service.list_models = AsyncMock(return_value=[m1, m2])
        service.update_health_status = AsyncMock()
        checker = SimpleNamespace(
            check_model=AsyncMock(
                side_effect=[
                    SimpleNamespace(status=HealthStatus.HEALTHY, latency_ms=10, error=None),
                    SimpleNamespace(status=HealthStatus.UNAVAILABLE, latency_ms=None, error="conn refused"),
                ]
            )
        )
        session = AsyncMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            "app.services.model_health_checker.get_health_checker", MagicMock(return_value=checker)
        ):
            response = await models_router.health_check_all_models(
                session=session, user=SimpleNamespace(), admin_user=SimpleNamespace()
            )
        service.list_models.assert_awaited_once_with(enabled_only=True)
        checker.check_model.assert_any_await(m1, session=session)
        checker.check_model.assert_any_await(m2, session=session)
        assert service.update_health_status.await_count == 2
        assert response == {
            "total": 2,
            "healthy": 1,
            "unhealthy": 1,
            "results": [
                {"model_id": str(m1.id), "alias": "a", "status": "healthy", "latency_ms": 10, "error": None},
                {"model_id": str(m2.id), "alias": "b", "status": "unavailable", "latency_ms": None, "error": "conn refused"},
            ],
        }

    async def test_checker_failure_becomes_500(self):
        service = MagicMock()
        service.list_models = AsyncMock(return_value=[make_model()])
        checker = SimpleNamespace(check_model=AsyncMock(side_effect=RuntimeError("nope")))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            "app.services.model_health_checker.get_health_checker", MagicMock(return_value=checker)
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.health_check_all_models(
                    session=AsyncMock(), user=SimpleNamespace(), admin_user=SimpleNamespace()
                )
        assert err.value.status_code == 500
        assert "Failed to health check models" in err.value.detail


class TestHealthCheckModel:
    async def test_health_check_returns_result_and_persists_status(self):
        model = make_model()
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=model)
        service.update_health_status = AsyncMock()
        checker = SimpleNamespace(
            check_model=AsyncMock(
                return_value=SimpleNamespace(status=HealthStatus.HEALTHY, latency_ms=5, error=None)
            )
        )
        session = AsyncMock()
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            "app.services.model_health_checker.get_health_checker", MagicMock(return_value=checker)
        ):
            response = await models_router.health_check_model(
                str(MODEL_ID),
                HealthCheckRequest(force=True),
                session=session,
                user=SimpleNamespace(),
                admin_user=SimpleNamespace(),
            )
        checker.check_model.assert_awaited_once_with(model, session=session)
        service.update_health_status.assert_awaited_once_with(
            MODEL_ID, HealthStatus.HEALTHY, latency_ms=5, error=None
        )
        assert response["model_id"] == str(MODEL_ID)
        assert response["alias"] == "emb.default"
        assert response["status"] == "healthy"
        assert response["latency_ms"] == 5
        assert isinstance(response["checked_at"], datetime)

    async def test_not_found(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)):
            with pytest.raises(HTTPException) as err:
                await models_router.health_check_model(
                    str(MODEL_ID),
                    HealthCheckRequest(),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 404

    async def test_checker_failure_becomes_500(self):
        service = MagicMock()
        service.get_by_id = AsyncMock(return_value=make_model())
        checker = SimpleNamespace(check_model=AsyncMock(side_effect=RuntimeError("boom")))
        with patch(f"{MODULE}.ModelService", MagicMock(return_value=service)), patch(
            "app.services.model_health_checker.get_health_checker", MagicMock(return_value=checker)
        ):
            with pytest.raises(HTTPException) as err:
                await models_router.health_check_model(
                    str(MODEL_ID),
                    HealthCheckRequest(),
                    session=AsyncMock(),
                    user=SimpleNamespace(),
                    admin_user=SimpleNamespace(),
                )
        assert err.value.status_code == 500
