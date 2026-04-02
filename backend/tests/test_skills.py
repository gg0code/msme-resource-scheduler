"""
tests/test_skills.py
--------------------
Integration tests for the Skills CRUD API (/api/skills/).
Each test uses the `client` and `auth_headers` fixtures which wrap requests
in a rolled-back transaction, so tests are fully isolated and can run in any order.
"""


def test_create_skill(client, auth_headers):
    """
    Verify that POST /api/skills/ creates a new skill and returns HTTP 201.
    Input  : Valid skill payload with name, category, is_premium.
    Output : HTTP 201 with the created skill JSON; is_active defaults to True.
    """
    resp = client.post(
        "/api/skills/",
        json={"name": "CNC Operation", "category": "generic", "is_premium": False},
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["name"] == "CNC Operation"
    assert data["is_active"] is True


def test_list_skills(client, auth_headers):
    """
    Verify that GET /api/skills/ returns all skills including newly created ones.
    Input  : One skill pre-created in the test.
    Output : HTTP 200 with a list of at least one skill.
    """
    client.post(
        "/api/skills/",
        json={"name": "Welding", "category": "premium", "is_premium": True},
        headers=auth_headers,
    )
    resp = client.get("/api/skills/", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_skill(client, auth_headers):
    """
    Verify that GET /api/skills/{id} returns the correct skill by ID.
    Input  : A skill created in the test; its id retrieved from the create response.
    Output : HTTP 200 with the matching skill JSON.
    """
    create_resp = client.post(
        "/api/skills/",
        json={"name": "Grinding", "category": "generic"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
    skill_id = create_resp.json()["id"]
    resp = client.get(f"/api/skills/{skill_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == skill_id


def test_update_skill(client, auth_headers):
    """
    Verify that PATCH /api/skills/{id} applies partial updates correctly.
    Input  : A skill created with is_premium=False; PATCH sets is_premium=True.
    Output : HTTP 200 with is_premium updated to True; other fields unchanged.
    """
    create_resp = client.post(
        "/api/skills/",
        json={"name": "Painting", "category": "generic"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
    skill_id = create_resp.json()["id"]
    resp = client.patch(
        f"/api/skills/{skill_id}",
        json={"is_premium": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_premium"] is True


def test_delete_skill(client, auth_headers):
    """
    Verify that DELETE /api/skills/{id} removes the skill and returns HTTP 204.
    Input  : A skill created in the test.
    Output : HTTP 204 No Content on success.
    """
    create_resp = client.post(
        "/api/skills/",
        json={"name": "Drilling", "category": "generic"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
    skill_id = create_resp.json()["id"]
    resp = client.delete(f"/api/skills/{skill_id}", headers=auth_headers)
    assert resp.status_code == 204
