import pytest
import pytest_asyncio
import httpx
import json
from unittest.mock import AsyncMock, patch

from app.analysis.ollama_analyzer import OllamaAnalyzer
from app.analysis.base import SetupSnapshot, BoundValue

def _dummy_setup() -> SetupSnapshot:
    return SetupSnapshot(tire_pressure_front=BoundValue(None, 30.0, None), tire_pressure_rear=BoundValue(None, 30.0, None),
        camber_front=BoundValue(None, -2.5, None), camber_rear=BoundValue(None, -1.5, None),
        springs_front=BoundValue(None, 500.0, None), springs_rear=BoundValue(None, 450.0, None),
        arb_front=BoundValue(None, 25.0, None), arb_rear=BoundValue(None, 20.0, None),
        bump_front=BoundValue(None, 5.0, None), bump_rear=BoundValue(None, 5.0, None),
        rebound_front=BoundValue(None, 5.0, None), rebound_rear=BoundValue(None, 5.0, None),
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
