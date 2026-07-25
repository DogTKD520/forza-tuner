import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.db.database import get_session

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def override_get_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(name="client")
def client_fixture():
    SQLModel.metadata.create_all(engine)
    with TestClient(app) as client:
        # Also clean up app state
        client.app.state.active_session_id = None
        if hasattr(client.app.state, "processor"):
            if client.app.state.processor.is_recording:
                client.app.state.processor.stop_recording()
        yield client
    SQLModel.metadata.drop_all(engine)


def test_start_session_overlapping_fails(client: TestClient):
    # First start should succeed
    response = client.post("/api/sessions/start")
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    
    # Second start should fail with 409
    response2 = client.post("/api/sessions/start")
    assert response2.status_code == 409
    assert "already active" in response2.json()["detail"]


def test_stop_session_invalid_id_fails(client: TestClient):
    # Start session
    response = client.post("/api/sessions/start")
    assert response.status_code == 201
    active_id = response.json()["session_id"]
    
    # Try to stop with a wrong ID
    wrong_id = str(active_id) + "_wrong"
    response = client.post(f"/api/sessions/{wrong_id}/stop")
    assert response.status_code == 409
    assert "does not match active session" in response.json()["detail"]


def test_stop_session_success_clears_active(client: TestClient):
    response = client.post("/api/sessions/start")
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    
    # Stop the active session
    response = client.post(f"/api/sessions/{session_id}/stop")
    assert response.status_code == 200
    
    # The active_session_id should be cleared
    # Try stopping again (should fail because no active recording)
    response = client.post(f"/api/sessions/{session_id}/stop")
    assert response.status_code == 400
    assert "No active recording session" in response.json()["detail"]


def test_stop_without_start_fails(client: TestClient):
    response = client.post("/api/sessions/1/stop")
    assert response.status_code == 400
    assert "No active recording session" in response.json()["detail"]
