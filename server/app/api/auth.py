from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import AuthResponse, LoginRequest, RegisterRequest, UpdateProfileRequest, UserResponse
from app.services.user_service import UserService

router = APIRouter(tags=["auth"])


def _resolve_user(service: UserService, token: str) -> User:
    user = service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired user token.")
    return user


def _to_user_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        avatar_preset=user.avatar_preset,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.post("/auth/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    service = UserService(db)
    try:
        user, token = service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthResponse(token=token, user=_to_user_response(user))


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    service = UserService(db)
    try:
        user, token = service.login(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse(token=token, user=_to_user_response(user))


@router.get("/me", response_model=UserResponse)
def me(x_user_token: str = Header(default=""), db: Session = Depends(get_db)):
    service = UserService(db)
    user = _resolve_user(service, x_user_token)
    return _to_user_response(user)


@router.patch("/me/profile", response_model=UserResponse)
def update_profile(payload: UpdateProfileRequest, x_user_token: str = Header(default=""), db: Session = Depends(get_db)):
    service = UserService(db)
    user = _resolve_user(service, x_user_token)
    updated = service.update_profile(user=user, display_name=payload.display_name, avatar_preset=payload.avatar_preset)
    return _to_user_response(updated)


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    x_user_token: str = Header(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = _resolve_user(service, x_user_token)
    try:
        updated = await service.save_avatar_upload(user=user, upload=file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_user_response(updated)
