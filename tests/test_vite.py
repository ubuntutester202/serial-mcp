import pytest
from fastapi.testclient import TestClient
from serial_mcp.webapp import app

def test_vite_client_dummy():
    with TestClient(app) as client:
        # Test exact path
        response = client.get("/@vite/client")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/javascript"
        
        # Test encoded path (TestClient might auto-encode or handle it, 
        # but usually we pass the path as string. 
        # The server receives decoded path.
        
        # If we manually encode:
        response = client.get("/%40vite/client")
        assert response.status_code == 200
