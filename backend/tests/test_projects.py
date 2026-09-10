def get_token(client, email, password):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_viewer_cannot_create_project(client):
    token = get_token(client, "viewer@infrapm.gov", "View@123")

    departments = client.get(
        "/api/v1/departments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert departments.status_code == 200
    department_id = departments.json()[0]["id"]

    pm_token = get_token(client, "pm@infrapm.gov", "PM@123")
    projects = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {pm_token}"},
    )
    assert projects.status_code == 200

    # Viewer is authenticated but does not have project-create permission.
    payload = {
        "code": "TEST-VIEWER-001",
        "name": "Unauthorized Test Project",
        "dept_id": department_id,
        "pm_id": projects.json()[0]["pm_id"] if projects.json() else "00000000-0000-0000-0000-000000000000",
        "total_estimated_cost": "10.00",
        "start_date": "2026-09-01",
        "expected_completion": "2027-09-01",
    }
    response = client.post(
        "/api/v1/projects",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_projects_are_readable_by_authenticated_user(client):
    token = get_token(client, "viewer@infrapm.gov", "View@123")
    response = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
