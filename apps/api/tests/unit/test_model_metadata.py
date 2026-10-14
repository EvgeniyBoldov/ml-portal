from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.services.model_metadata_service import discovered_characteristics, ModelMetadataService
from app.schemas.model_registry import ModelProbeRequest


def model(manifest):
    return SimpleNamespace(type='embedding', provider_model_name='encoder', connector='local_emb_http',
                           base_url='http://encoder', instance_id=None, model_version='v1',
                           embedding_dimensions=384, max_input_tokens=256,
                           extra_config={'manifest':manifest})


def test_type_specific_characteristics_do_not_invent_missing_values():
    assert discovered_characteristics({'dimensions':0, 'version':'', 'max_tokens':None}, 'reranker') == {}
    assert discovered_characteristics({'dimensions':1024, 'max_tokens':8192}, 'embedding') == {'embedding_dimensions':1024, 'max_input_tokens':8192}
    assert discovered_characteristics({'dimensions':1024, 'context_window_tokens':32768}, 'llm_chat') == {'context_window_tokens':32768}
    with pytest.raises(ValueError):
        ModelProbeRequest(instance_id={'invalid':'uuid'})


@pytest.mark.asyncio
async def test_discovered_field_is_read_only_but_missing_field_remains_editable():
    current = model({'dimensions':384})
    with pytest.raises(ValueError, match='supplied by the service'):
        await ModelMetadataService.prepare_write(AsyncMock(), {'embedding_dimensions':1024}, current)
    prepared = await ModelMetadataService.prepare_write(AsyncMock(), {'max_input_tokens':512}, current)
    assert prepared['max_input_tokens'] == 512


@pytest.mark.asyncio
async def test_changing_endpoint_invalidates_old_discovery():
    prepared = await ModelMetadataService.prepare_write(AsyncMock(), {'base_url':'http://new', 'embedding_dimensions':1024}, model({'dimensions':384}))
    assert 'manifest' not in prepared['extra_config']
    assert prepared['capabilities_checked_at'] is None


@pytest.mark.asyncio
async def test_client_manifest_is_rechecked_on_save(monkeypatch):
    from app.services import model_metadata_service as metadata
    monkeypatch.setattr(metadata, '_probe_manifest', AsyncMock(return_value=({'dimensions':1024, 'max_tokens':8192}, 'healthy')))
    prepared = await ModelMetadataService.prepare_write(AsyncMock(), {'embedding_dimensions':999,
        'extra_config':{'manifest':{'dimensions':999}}}, model({'dimensions':384}))
    assert prepared['embedding_dimensions'] == 1024
    assert prepared['extra_config']['manifest']['dimensions'] == 1024
    assert prepared['capabilities_checked_at'] is not None


@pytest.mark.asyncio
async def test_probe_returns_partial_metadata_and_forwards_selected_model(monkeypatch):
    from app.api.v1.routers.admin import models
    probe = AsyncMock(return_value=({'dimensions':1024}, 'healthy'))
    monkeypatch.setattr(models, '_probe_manifest', probe)
    response = await models.probe_model_info(ModelProbeRequest(base_url='http://encoder', connector='local_emb_http', provider_model_name='bge-m3'), AsyncMock(), None, None)
    assert response['raw'] == {'dimensions':1024}
    assert response['model_version'] == ''
    assert probe.call_args.kwargs['provider_model_name'] == 'bge-m3'
    assert probe.call_args.kwargs['connector'] == 'local_emb_http'


@pytest.mark.asyncio
async def test_probe_failure_allows_manual_characteristics(monkeypatch):
    from app.api.v1.routers.admin import models
    monkeypatch.setattr(models, '_probe_manifest', AsyncMock(side_effect=ValueError('No metadata')))
    response = await models.probe_model_info(ModelProbeRequest(base_url='http://encoder'), AsyncMock(), None, None)
    assert response.raw == {}
    assert response.warning
    assert response.health_status == 'unknown'


def test_text_modality_does_not_guess_embedding_type():
    from app.services.model_metadata_service import _map_modality_to_model_type
    assert _map_modality_to_model_type('text') is None
    assert _map_modality_to_model_type('embedding') == 'embedding'
    assert _map_modality_to_model_type('llm_chat') == 'llm_chat'
    assert _map_modality_to_model_type('reranker') == 'reranker'


@pytest.mark.asyncio
async def test_health_does_not_report_unloaded_model_as_healthy(httpx_mock):
    from app.services.model_metadata_service import _probe_manifest
    httpx_mock.add_response(url='http://encoder/health', json={'status':'ok', 'model_loaded':False})
    httpx_mock.add_response(url='http://encoder/description', json={'alias':'encoder', 'modality':'reranker'})
    manifest, status = await _probe_manifest('http://encoder', connector='local_rerank_http')
    assert status == 'unavailable'
    assert 'version' not in manifest
