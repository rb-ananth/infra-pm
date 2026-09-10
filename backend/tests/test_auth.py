def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_success(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@infrapm.gov", "password": "Admin@123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_failure(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@infrapm.gov", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_me(client):
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@infrapm.gov", "password": "Admin@123"},
    )
    token = login.json()["access_token"]

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "admin@infrapm.gov"
