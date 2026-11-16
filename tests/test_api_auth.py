import pytest
from fastapi import HTTPException
from models.schemas import ChatResponse

from api.main import app, require_api_token


def test_api_authentication_is_allowed_without_token_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.main.settings.api_auth_token", "")
    monkeypatch.setattr("api.main.settings.environment", "development")

    assert require_api_token(None) is None


def test_api_authentication_fails_closed_without_token_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.main.settings.api_auth_token", "")
    monkeypatch.setattr("api.main.settings.environment", "production")

    with pytest.raises(HTTPException) as error:
        require_api_token(None)

    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "authorization",
    [None, "Basic secret", "Bearer wrong-token"],
)
def test_api_authentication_rejects_missing_or_invalid_tokens(
    monkeypatch: pytest.MonkeyPatch,
    authorization: str | None,
) -> None:
    monkeypatch.setattr("api.main.settings.api_auth_token", "expected-token")
    monkeypatch.setattr("api.main.settings.environment", "development")

    with pytest.raises(HTTPException) as error:
        require_api_token(authorization)

    assert error.value.status_code == 401


def test_api_authentication_accepts_matching_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.main.settings.api_auth_token", "expected-token")
    monkeypatch.setattr("api.main.settings.environment", "development")

    assert require_api_token("Bearer expected-token") is None


def test_sensitive_api_routes_require_authentication() -> None:
    protected_paths = {
        "/chat",
        "/conversations/{conversation_id}",
        "/documents",
        "/documents/{document_name}/chunks",
    }
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) in protected_paths
    ]

    assert {route.path for route in routes} == protected_paths
    assert all(
        any(dependency.call is require_api_token for dependency in route.dependant.dependencies)
        for route in routes
    )


def test_chat_response_does_not_treat_reranker_score_as_probability() -> None:
    response = ChatResponse(
        answer="Grounded answer",
        reranker_score=-0.42,
        sources=[],
        conversation_id="conversation-a",
    )

    assert response.reranker_score == -0.42
