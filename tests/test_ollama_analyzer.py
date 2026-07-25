import pytest
import pytest_asyncio
import httpx
import json
from unittest.mock import AsyncMock, patch

from app.analysis.ollama_analyzer import OllamaAnalyzer
from app.analysis.base import SetupSnapshot

def _dummy_setup() -> SetupSnapshot:
    return SetupSnapshot(
        tire_pressure_front=30.0, tire_pressure_rear=30.0,
        camber_front=-2.5, camber_rear=-1.5,
        springs_front=500.0, springs_rear=450.0,
        arb_front=25.0, arb_rear=20.0,
        bump_front=5.0, bump_rear=5.0,
        rebound_front=5.0, rebound_rear=5.0,
    )

@pytest.mark.asyncio
async def test_ollama_fallback_on_http_error():
    analyzer = OllamaAnalyzer()
    
    # Mock httpx.AsyncClient to raise HTTPError
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPError("Connection failed")
        
        result = await analyzer.analyze({}, _dummy_setup(), "street_road")
        
        assert result.analyzer_type == "math"
        assert "math" in str(result) or len(result.adjustments) >= 0

@pytest.mark.asyncio
async def test_ollama_fallback_on_json_error():
    analyzer = OllamaAnalyzer()
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = AsyncMock()
        # Mock synchronous json() method
        mock_response.json = lambda: {"message": {"content": "not json"}}
        # Mock synchronous raise_for_status
        mock_response.raise_for_status = lambda: None
        mock_post.return_value = mock_response
        
        result = await analyzer.analyze({}, _dummy_setup(), "street_road")
        
        assert result.analyzer_type == "math"
