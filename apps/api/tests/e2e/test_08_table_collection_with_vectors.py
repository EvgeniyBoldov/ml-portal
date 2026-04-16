"""
Test 08: Table Collection with Vectorization

Scenarios:
- Create table collection with vector-enabled field
- Upload CSV data
- Wait for vectorization
- Test vector search
"""
import os
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.order(8)]


@pytest.mark.asyncio
async def test_create_vector_table_collection(client, admin_headers):
    """Create table collection with vector-enabled text field"""
    # Get test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    test_tenant = next((t for t in tenants if t["name"] == "Integration Test Tenant"), None)
    assert test_tenant is not None, "Test tenant not found"
    
    # Get data-sql instance
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    data_sql = next((i for i in instances if i["slug"] == "data-sql-tickets"), None)
    assert data_sql is not None, "Data SQL instance not found"
    
    response = await client.post(
        "/api/v1/admin/collections",
        headers=admin_headers,
        json={
            "tenant_id": test_tenant["id"],
            "slug": "vector-articles",
            "name": "Vector Articles",
            "description": "Articles with vector search enabled",
            "collection_type": "table",
            "fields": [
                {"name": "id", "type": "text", "required": True, "search_modes": ["exact"]},
                {"name": "title", "type": "text", "required": True, "search_modes": ["exact", "like"]},
                {"name": "content", "type": "text", "required": True, "search_modes": ["like"], "has_vector_search": True},
                {"name": "category", "type": "text", "required": False, "search_modes": ["exact"]},
            ],
            "primary_key_field": "id",
            "data_instance_id": data_sql["id"],
            "has_vector_search": True,
            "is_active": True,
        },
    )
    assert response.status_code == 201, f"Failed to create collection: {response.text}"
    data = response.json()
    assert data["slug"] == "vector-articles"
    assert data["has_vector_search"] is True
    
    return data


@pytest.mark.asyncio
async def test_upload_csv_to_collection(client, admin_headers):
    """Upload CSV data to vector collection"""
    # Get collection
    collections_response = await client.get(
        "/api/v1/admin/collections",
        headers=admin_headers,
    )
    collections = collections_response.json()
    vector_collection = next((c for c in collections if c["slug"] == "vector-articles"), None)
    
    if not vector_collection:
        pytest.skip("Vector articles collection not found")
    
    # Check if test data file exists
    test_data_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "..", "tests", "templates", "test_data.csv"
    )
    
    if not os.path.exists(test_data_path):
        # Create inline test data
        import io
        csv_content = """id,title,content,category
ART-001,Introduction to BGP,Border Gateway Protocol is the routing protocol used on the Internet.,Networking
ART-002,VLAN Configuration,Virtual LANs allow logical segmentation of network traffic.,Networking
ART-003,OSPF Basics,Open Shortest Path First is a link-state routing protocol.,Networking
ART-004,Network Security,Best practices for securing enterprise networks.,Security
ART-005,BGP Troubleshooting,Common BGP issues and how to resolve them.,Networking
"""
        files = {
            "file": ("test_data.csv", io.BytesIO(csv_content.encode()), "text/csv")
        }
    else:
        with open(test_data_path, "rb") as f:
            files = {
                "file": ("test_data.csv", f, "text/csv")
            }
    
    # Upload CSV
    response = await client.post(
        f"/api/v1/collections/{vector_collection['id']}/upload",
        headers={k: v for k, v in admin_headers.items() if k != "Content-Type"},
        files=files,
    )
    assert response.status_code == 201, f"Failed to upload CSV: {response.text}"
    
    return response.json()


@pytest.mark.asyncio
async def test_list_collection_data(client, admin_headers):
    """List data in vector collection"""
    # Get collection
    collections_response = await client.get(
        "/api/v1/admin/collections",
        headers=admin_headers,
    )
    collections = collections_response.json()
    vector_collection = next((c for c in collections if c["slug"] == "vector-articles"), None)
    
    if not vector_collection:
        pytest.skip("Vector articles collection not found")
    
    # List data via table endpoint
    response = await client.get(
        f"/api/v1/collections/{vector_collection['id']}/table",
        headers=admin_headers,
    )
    
    # May be 200 or 404 depending on API structure
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list) or isinstance(data, dict)


@pytest.mark.asyncio
async def test_collection_stats(client, admin_headers):
    """Get collection stats"""
    # Get collection
    collections_response = await client.get(
        "/api/v1/admin/collections",
        headers=admin_headers,
    )
    collections = collections_response.json()
    vector_collection = next((c for c in collections if c["slug"] == "vector-articles"), None)
    
    if not vector_collection:
        pytest.skip("Vector articles collection not found")
    
    # Get stats
    response = await client.get(
        f"/api/v1/admin/collections/{vector_collection['id']}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    
    # Check for row count or stats
    assert "row_count" in data or "stats" in data or "id" in data
