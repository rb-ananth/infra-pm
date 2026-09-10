def test_audit_logs_are_read_only(client):
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@infrapm.gov", "password": "Admin@123"},
    )
    token = login.json()["access_token"]

    response = client.put(
        "/api/v1/audit-logs/some-id",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 404

    response = client.delete(
        "/api/v1/audit-logs/some-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
