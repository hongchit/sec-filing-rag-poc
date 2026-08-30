from __future__ import annotations

from typing import Annotated, cast

from authlib.integrations.starlette_client import OAuth, OAuthError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response

from ....auth import AuthRepository, Principal
from ....core.config import Settings
from ...dependencies import auth_repository, current_user, settings

router = APIRouter(prefix="/auth", tags=["authentication"])


def _oauth(config: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        "google",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )
    return oauth


@router.get("/google/login")
async def google_login(
    request: Request,
    config: Annotated[Settings, Depends(settings)],
    return_to: Annotated[str, Query(pattern=r"^/(?:[^/].*)?$")] = "/research",
    policy_acknowledged: Annotated[bool, Query()] = False,
) -> RedirectResponse:
    if not policy_acknowledged:
        raise HTTPException(400, detail={"code": "policy_acknowledgement_required"})
    request.session["return_to"] = return_to
    request.session["policy_acknowledged"] = True
    callback = f"{config.public_base_url.rstrip('/')}/api/auth/google/callback"
    return cast(RedirectResponse, await _oauth(config).google.authorize_redirect(request, callback))


@router.get("/google/callback")
async def google_callback(
    request: Request,
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    config: Annotated[Settings, Depends(settings)],
) -> RedirectResponse:
    if request.session.pop("policy_acknowledged", False) is not True:
        raise HTTPException(400, detail={"code": "policy_acknowledgement_required"})
    try:
        token = await _oauth(config).google.authorize_access_token(request)
        profile = token["userinfo"]
    except (OAuthError, KeyError):
        raise HTTPException(401, detail={"code": "google_authentication_failed"}) from None
    if not profile.get("email_verified") or not profile.get("email"):
        raise HTTPException(403, detail={"code": "verified_email_required"})
    user = repository.upsert_google_user(
        issuer=str(profile["iss"]),
        subject=str(profile["sub"]),
        email=str(profile["email"]),
        name=profile.get("name"),
    )
    if user["status"] != "active":
        repository.audit("login", "disabled", actor=user["id"])
        raise HTTPException(403, detail={"code": "account_disabled"})
    session_token, csrf_token = repository.create_session(user["id"], config.session_lifetime_days)
    repository.audit(
        "login",
        "succeeded",
        actor=user["id"],
        metadata={
            "terms_accepted": True,
            "privacy_notice_acknowledged": True,
            "cookie_notice_acknowledged": True,
        },
    )
    destination = request.session.pop("return_to", "/research")
    response = RedirectResponse(destination, status_code=303)
    secure = config.public_base_url.startswith("https://")
    session_name = "__Host-sec-rag-session" if secure else "sec-rag-session"
    response.set_cookie(
        session_name,
        session_token,
        max_age=config.session_lifetime_days * 86400,
        secure=secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "sec-rag-csrf",
        csrf_token,
        max_age=config.session_lifetime_days * 86400,
        secure=secure,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me")
def me(
    user: Annotated[Principal, Depends(current_user)],
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    config: Annotated[Settings, Depends(settings)],
) -> dict[str, object]:
    return {
        "user_id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "budget": repository.budget(user.id, config.default_user_lifetime_budget_usd),
        "action_reservations": {
            "research_usd": format(config.research_cost_reservation_usd, "f"),
            "corpus_preparation_usd": format(config.corpus_preparation_cost_reservation_usd, "f"),
        },
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    user: Annotated[Principal, Depends(current_user)],
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    config: Annotated[Settings, Depends(settings)],
) -> Response:
    token = request.cookies.get("__Host-sec-rag-session") or request.cookies.get("sec-rag-session")
    if token:
        repository.revoke_session(token)
    repository.audit("logout", "succeeded", actor=user.id)
    response = Response(status_code=204)
    response.delete_cookie("__Host-sec-rag-session", path="/", secure=True)
    response.delete_cookie("sec-rag-session", path="/")
    response.delete_cookie(
        "sec-rag-csrf", path="/", secure=config.public_base_url.startswith("https://")
    )
    return response
