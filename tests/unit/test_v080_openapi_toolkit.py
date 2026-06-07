"""v0.8.0: OpenAPI Toolkit tests.

Validates that any OpenAPI 3.x or Swagger 2.x spec produces working
LARGESTACK tools. Uses respx to mock HTTP calls.
"""

from __future__ import annotations

import json
import pytest

respx = pytest.importorskip("respx")


# -------------------- minimal specs as fixtures --------------------

PETSTORE_OPENAPI_3 = {
    "openapi": "3.0.0",
    "info": {"title": "Petstore", "version": "1.0"},
    "servers": [{"url": "https://petstore.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List all pets",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                ],
            },
            "post": {
                "operationId": "createPet",
                "summary": "Create a pet",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "tag": {"type": "string"},
                                },
                                "required": ["name"],
                            }
                        }
                    },
                },
            },
        },
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "summary": "Get a pet by ID",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    },
                ],
            },
            "delete": {
                "operationId": "deletePet",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                    },
                ],
            },
        },
    },
}

SWAGGER_2 = {
    "swagger": "2.0",
    "info": {"title": "Old API", "version": "1.0"},
    "host": "old.example.com",
    "basePath": "/api",
    "schemes": ["https"],
    "paths": {"/users": {"get": {"operationId": "listUsers", "summary": "List users"}}},
}


# -------------------- Construction --------------------


def test_constructor_rejects_empty_spec():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    with pytest.raises(ValueError, match="non-empty dict"):
        OpenAPIToolkit({})
    with pytest.raises(ValueError):
        OpenAPIToolkit(None)  # type: ignore


def test_resolves_base_url_from_openapi_3():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    assert tk.base_url == "https://petstore.example.com/v1"


def test_resolves_base_url_from_swagger_2():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(SWAGGER_2)
    assert tk.base_url == "https://old.example.com/api"


def test_base_url_override_takes_precedence():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3, base_url="https://override.test/v2")
    assert tk.base_url == "https://override.test/v2"


def test_generates_one_tool_per_operation():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    tools = tk.get_tools()
    # 4 operations: GET /pets, POST /pets, GET /pets/{id}, DELETE /pets/{id}
    assert len(tools) == 4
    names = {t._tool_schema["name"] for t in tools}
    assert names == {"listPets", "createPet", "getPet", "deletePet"}


def test_tool_descriptions_include_summary():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    tools = tk.get_tools()
    list_pets = next(t for t in tools if t._tool_schema["name"] == "listPets")
    assert "List all pets" in list_pets._tool_schema["description"]


def test_tool_schema_includes_path_query_and_body_params():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    tools = tk.get_tools()

    list_pets = next(t for t in tools if t._tool_schema["name"] == "listPets")
    schema = list_pets._openapi_schema
    assert "limit" in schema["properties"]
    assert schema["properties"]["limit"]["type"] == "integer"

    create_pet = next(t for t in tools if t._tool_schema["name"] == "createPet")
    create_schema = create_pet._openapi_schema
    assert "body" in create_schema["properties"]
    assert "body" in create_schema["required"]

    get_pet = next(t for t in tools if t._tool_schema["name"] == "getPet")
    get_schema = get_pet._openapi_schema
    assert "petId" in get_schema["properties"]
    assert "petId" in get_schema["required"]


def test_safe_tool_name_fallback_when_no_operationId():
    """An op without operationId should still produce a callable tool."""
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    spec = {
        "openapi": "3.0.0",
        "info": {"title": "x", "version": "1"},
        "servers": [{"url": "https://x.test"}],
        "paths": {"/foo/bar": {"get": {"summary": "no op id"}}},
    }
    tk = OpenAPIToolkit(spec)
    tools = tk.get_tools()
    assert len(tools) == 1
    name = tools[0]._tool_schema["name"]
    # Must be a valid identifier-like string
    assert name and name.replace("_", "").isalnum()


# -------------------- Execution --------------------


@pytest.mark.asyncio
async def test_get_tool_substitutes_path_param_and_returns_body():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    get_pet = next(t for t in tk.get_tools() if t._tool_schema["name"] == "getPet")

    with respx.mock() as mock:
        mock.get("https://petstore.example.com/v1/pets/42").respond(
            200, json={"id": 42, "name": "Rex"}
        )
        out = await get_pet(petId=42)

    payload = json.loads(out)
    assert payload["status"] == 200
    assert "Rex" in payload["body"]


@pytest.mark.asyncio
async def test_post_tool_sends_json_body():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    create_pet = next(t for t in tk.get_tools() if t._tool_schema["name"] == "createPet")

    with respx.mock() as mock:
        route = mock.post("https://petstore.example.com/v1/pets").respond(201, json={"id": 1})
        out = await create_pet(body={"name": "Rex", "tag": "dog"})

    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"name": "Rex", "tag": "dog"}
    payload = json.loads(out)
    assert payload["status"] == 201


@pytest.mark.asyncio
async def test_query_params_passed_through():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    list_pets = next(t for t in tk.get_tools() if t._tool_schema["name"] == "listPets")

    with respx.mock() as mock:
        route = mock.get("https://petstore.example.com/v1/pets").respond(200, json=[])
        await list_pets(limit=5)

    assert route.called
    assert "limit=5" in str(route.calls.last.request.url)


@pytest.mark.asyncio
async def test_auth_header_applied_to_all_requests():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(
        PETSTORE_OPENAPI_3,
        auth_header=("Authorization", "Bearer test-token"),
    )
    list_pets = next(t for t in tk.get_tools() if t._tool_schema["name"] == "listPets")

    with respx.mock() as mock:
        route = mock.get("https://petstore.example.com/v1/pets").respond(200, json=[])
        await list_pets()

    assert route.calls.last.request.headers["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_api_key_query_appended():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(
        PETSTORE_OPENAPI_3,
        api_key_query={"api_key": "secret"},
    )
    list_pets = next(t for t in tk.get_tools() if t._tool_schema["name"] == "listPets")

    with respx.mock() as mock:
        route = mock.get("https://petstore.example.com/v1/pets").respond(200, json=[])
        await list_pets()

    assert "api_key=secret" in str(route.calls.last.request.url)


@pytest.mark.asyncio
async def test_http_error_returned_as_dict_not_exception():
    """Failed HTTP returns the response — agent loop survives."""
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    get_pet = next(t for t in tk.get_tools() if t._tool_schema["name"] == "getPet")

    with respx.mock() as mock:
        mock.get("https://petstore.example.com/v1/pets/99").respond(
            404, json={"error": "not found"}
        )
        out = await get_pet(petId=99)
    payload = json.loads(out)
    assert payload["status"] == 404


@pytest.mark.asyncio
async def test_network_error_returns_string_not_exception():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    get_pet = next(t for t in tk.get_tools() if t._tool_schema["name"] == "getPet")

    import httpx

    with respx.mock() as mock:
        mock.get("https://petstore.example.com/v1/pets/1").mock(
            side_effect=httpx.ConnectError("network down")
        )
        out = await get_pet(petId=1)

    # Returned as string, NOT raised
    assert isinstance(out, str)
    assert "failed" in out.lower() or "error" in out.lower()


@pytest.mark.asyncio
async def test_response_truncation_for_huge_bodies():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3, max_response_chars=100)
    list_pets = next(t for t in tk.get_tools() if t._tool_schema["name"] == "listPets")

    huge = {"data": "x" * 5000}
    with respx.mock() as mock:
        mock.get("https://petstore.example.com/v1/pets").respond(200, json=huge)
        out = await list_pets()
    payload = json.loads(out)
    assert "truncated" in payload["body"]


def test_swagger_2_works():
    """Old Swagger 2.0 specs must still produce tools."""
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(SWAGGER_2)
    tools = tk.get_tools()
    assert len(tools) == 1
    assert tools[0]._tool_schema["name"] == "listUsers"


def test_len_returns_tool_count():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    tk = OpenAPIToolkit(PETSTORE_OPENAPI_3)
    assert len(tk) == 4


# -------------------- from_url --------------------


@pytest.mark.asyncio
async def test_from_url_fetches_and_parses_json():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    with respx.mock() as mock:
        mock.get("https://example.com/spec.json").respond(200, json=PETSTORE_OPENAPI_3)
        tk = await OpenAPIToolkit.from_url("https://example.com/spec.json")
    assert len(tk.get_tools()) == 4


@pytest.mark.asyncio
async def test_from_url_raises_on_404():
    from largestack._integrations.openapi_toolkit import OpenAPIToolkit

    with respx.mock() as mock:
        mock.get("https://example.com/missing.json").respond(404)
        with pytest.raises(ValueError, match="failed to fetch"):
            await OpenAPIToolkit.from_url("https://example.com/missing.json")
