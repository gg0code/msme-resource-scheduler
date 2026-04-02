"""
```python
"""
FILE PURPOSE
This file contains comprehensive integration tests for the Skills CRUD API endpoints (/api/skills/) in the ZetaOps Copilot workforce scheduling application. It validates that all HTTP operations (CREATE, READ, UPDATE, DELETE) work correctly for the Skills resource, which represents worker competencies and capabilities that can be assigned to employees and required by jobs. This test suite was introduced in v4-dev as part of the core scheduling feature set and ensures that skill management functionality operates correctly across all manufacturing industry types (printing, corrugated box, fabrication, chemical processing, field service). The file sits in the backend testing layer and uses pytest fixtures to provide isolated database transactions for each test.

WHAT THIS FILE DOES — step by step
1. Imports pytest testing framework and relies on `client` and `auth_headers` fixtures from conftest.py
2. Defines test_create_skill() which verifies POST /api/skills/ endpoint creates new skills with proper defaults
3. Defines test_list_skills() which verifies GET /api/skills/ endpoint returns all skills for the authenticated tenant
4. Defines test_get_skill() which verifies GET /api/skills/{id} endpoint retrieves individual skills by ID
5. Defines test_update_skill() which verifies PATCH /api/skills/{id} endpoint applies partial updates correctly
6. Defines test_delete_skill() which verifies DELETE /api/skills/{id} endpoint removes skills and returns proper HTTP status
7. Each test creates its own test data and verifies both HTTP status codes and response JSON structure
8. All tests run in isolated database transactions that are rolled back after completion

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : test_create_skill
Type         : pytest test function
Purpose      : Validates that the POST /api/skills/ endpoint correctly creates a new skill record with the provided name, category, and is_premium flag, while automatically setting is_active to True by default. Ensures the API returns HTTP 201 status and the complete skill object in JSON format.
Parameters   : client (TestClient fixture for making HTTP requests), auth_headers (dict with JWT authorization headers for tenant-scoped requests)
Returns      : None (pytest test function - assertions determine pass/fail)
Calls        : client.post() method to send HTTP POST request to skills API endpoint
DB/API       : Creates new skill record in database via POST /api/skills/ endpoint, automatically tenant-scoped
Side effects : Creates a skill record in the test database (rolled back after test completion)

Name         : test_list_skills
Type         : pytest test function  
Purpose      : Validates that the GET /api/skills/ endpoint returns a list of all skills belonging to the authenticated user's tenant. First creates a test skill to ensure at least one record exists, then verifies the list endpoint returns HTTP 200 and contains the expected data.
Parameters   : client (TestClient fixture for making HTTP requests), auth_headers (dict with JWT authorization headers for tenant-scoped requests)
Returns      : None (pytest test function - assertions determine pass/fail)
Calls        : client.post() to create test data, then client.get() to retrieve skills list
DB/API       : Creates skill via POST, then queries all skills via GET /api/skills/ (tenant-scoped)
Side effects : Creates a skill record in test database, then queries skills table

Name         : test_get_skill
Type         : pytest test function
Purpose      : Validates that the GET /api/skills/{id} endpoint correctly retrieves a specific skill by its unique identifier. Creates a test skill first, extracts its ID from the creation response, then verifies the get-by-id endpoint returns the exact same skill data.
Parameters   : client (TestClient fixture for making HTTP requests), auth_headers (dict with JWT authorization headers for tenant-scoped requests)
Returns      : None (pytest test function - assertions determine pass/fail)
Calls        : client.post() to create test skill, client.get() to retrieve specific skill by ID
DB/API       : Creates skill via POST /api/skills/, then retrieves via GET /api/skills/{id} (both tenant-scoped)
Side effects : Creates skill record, then performs database lookup by primary key

Name         : test_update_skill
Type         : pytest test function
Purpose      : Validates that the PATCH /api/skills/{id} endpoint correctly applies partial updates to existing skill records without affecting unchanged fields. Creates a skill with is_premium=False, then updates only the is_premium field to True while verifying other fields remain unchanged.
Parameters   : client (TestClient fixture for making HTTP requests), auth_headers (dict with JWT authorization headers for tenant-scoped requests)  
Returns      : None (pytest test function - assertions determine pass/fail)
Calls        : client.post() to create test skill, client.patch() to perform partial update
DB/API       : Creates skill via POST, then updates via PATCH /api/skills/{id} (both tenant-scoped)
Side effects : Creates skill record, then modifies specific fields in database

Name         : test_delete_skill
Type         : pytest test function
Purpose      : Validates that the DELETE /api/skills/{id} endpoint correctly removes skill records from the database and returns the proper HTTP 204 No Content status code. Creates a test skill first, then attempts to delete it and verifies the successful deletion response.
Parameters   : client (TestClient fixture for making HTTP requests), auth_headers (dict with JWT authorization headers for tenant-scoped requests)
Returns      : None (pytest test function - assertions determine pass/fail)  
Calls        : client.post() to create test skill, client.delete() to remove skill by ID
DB/API       : Creates skill via POST /api/skills/, then deletes via DELETE /api/skills/{id} (both tenant-scoped)
Side effects : Creates skill record, then removes it from database

WHO CALLS THIS FILE
This file is executed by the pytest test runner when running the backend test suite. It is not imported by other application code but is invoked by:
- pytest command line tool during local development testing
- CI/CD pipeline during automated testing on pull requests and deployments
- backend/conftest.py provides the fixtures (client, auth_headers) that this file depends on

IMPORTS EXPLAINED
This file has no explicit imports shown in the source code, but it implicitly depends on pytest framework fixtures and the FastAPI TestClient. The `client` fixture (from conftest.py) provides a TestClient instance configured with the FastAPI application and database session management. The `auth_headers` fixture provides JWT authentication headers with a valid access token for making authorized requests to tenant-scoped API endpoints.

INTERN NOTES
- Easiest thing to break without realising: Forgetting that all skills operations are tenant-scoped, so if you modify the auth_headers fixture or JWT token generation, these tests will fail with 401/403 errors even if the skills API logic is correct
- Non-obvious design decision and why: Each test creates its own test data instead of sharing fixtures because the `client` fixture wraps each test in a rolled-back database transaction, ensuring complete test isolation and preventing test order dependencies
- Most common mistake when editing: Adding assertions that check absolute counts (like "exactly 1 skill exists") instead of relative counts (like "at least 1 skill exists") because other tests might have created additional skills before this test runs
- Which design principle this file implements: Principle #2 (tenant scoping on ALL DB queries) - every API call in these tests automatically includes tenant filtering through the auth_headers JWT token
- What to check if this file behaves unexpectedly: Verify that backend/conftest.py fixtures are working correctly, check that the Skills model and CRUD operations in backend/app/models/ and backend/app/crud/ are properly tenant-scoped, and ensure the skills router in backend/app/routers/ is registered in main.py
- If v5-whatsapp only: Not applicable - this file
"""

def test_create_skill(client, auth_headers):
    """
    Verify that POST /api/skills/ creates a new skill and returns HTTP 201.

    Input  : Valid skill payload with name, category, is_premium.
    Output : HTTP 201 with the created skill JSON; is_active defaults to True.
    """
    resp = client.post("/api/skills/", json={"name": "CNC Operation", "category": "generic", "is_premium": False}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "CNC Operation"
    assert data["is_active"] is True


def test_list_skills(client, auth_headers):
    """
    Verify that GET /api/skills/ returns all skills including newly created ones.

    Input  : One skill pre-created in the test.
    Output : HTTP 200 with a list of at least one skill.
    """
    client.post("/api/skills/", json={"name": "Welding", "category": "premium", "is_premium": True}, headers=auth_headers)
    resp = client.get("/api/skills/", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_get_skill(client, auth_headers):
    """
    Verify that GET /api/skills/{id} returns the correct skill by ID.

    Input  : A skill created in the test; its id retrieved from the create response.
    Output : HTTP 200 with the matching skill JSON.
    """
    create_resp = client.post("/api/skills/", json={"name": "Grinding", "category": "generic"}, headers=auth_headers)
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
    create_resp = client.post("/api/skills/", json={"name": "Painting", "category": "generic"}, headers=auth_headers)
    skill_id = create_resp.json()["id"]
    resp = client.patch(f"/api/skills/{skill_id}", json={"is_premium": True}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_premium"] is True


def test_delete_skill(client, auth_headers):
    """
    Verify that DELETE /api/skills/{id} removes the skill and returns HTTP 204.

    Input  : A skill created in the test.
    Output : HTTP 204 No Content on success.
    """
    create_resp = client.post("/api/skills/", json={"name": "Drilling", "category": "generic"}, headers=auth_headers)
    skill_id = create_resp.json()["id"]
    resp = client.delete(f"/api/skills/{skill_id}", headers=auth_headers)
    assert resp.status_code == 204
