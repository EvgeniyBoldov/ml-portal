from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_HERE = Path(__file__).resolve()
_SERVER_PATH = next(
    (parent / "mcp" / "ml_inference" / "server.py" for parent in _HERE.parents if (parent / "mcp" / "ml_inference" / "server.py").exists()),
    None,
)
if _SERVER_PATH is None:
    pytest.skip("ML inference MCP shim is unavailable", allow_module_level=True)
_MCP_ROOT = _SERVER_PATH.parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))
_SPEC = spec_from_file_location("ml_inference_mcp_server_module", _SERVER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Cannot load ML inference MCP shim from {_SERVER_PATH}")
ml_server = module_from_spec(_SPEC)
_SPEC.loader.exec_module(ml_server)


def test_ml_inference_tools_expose_catalog_and_prediction_contracts():
    tools = {tool["name"]: tool for tool in ml_server.TOOLS}

    assert set(tools) == {"model.info", "model.predict"}
    assert tools["model.info"]["annotations"]["readOnlyHint"] is True
    assert tools["model.predict"]["annotations"]["readOnlyHint"] is True
    assert tools["model.predict"]["inputSchema"]["required"] == ["model_id", "inputs"]


def test_model_id_is_encoded_before_it_becomes_a_facade_path_segment():
    assert ml_server._path_for_model("risk/model 1") == "/v1/models/risk%2Fmodel%201"


def test_instance_context_is_the_default_facade_url_source():
    url = ml_server._extract_base_url({}, {"instance_context": {"data_instance_url": "https://inference.example/"}})

    assert url == "https://inference.example"


def test_mcp_rejects_oversized_facade_results():
    original = ml_server.MAX_RESPONSE_BYTES
    ml_server.MAX_RESPONSE_BYTES = 8
    try:
        with pytest.raises(ValueError, match="result limit"):
            ml_server._assert_bounded({"prediction": "too large"})
    finally:
        ml_server.MAX_RESPONSE_BYTES = original
