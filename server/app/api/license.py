from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import get_db
from app.schemas.license import (
    ActivateRequest,
    ActivateResponse,
    ExtendLicenseRequest,
    GenerateKeyRequest,
    GenerateKeyResponse,
    HubActionResponse,
    PatreonAuthResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.services.license_service import LicenseService
from app.services.patreon_service import PatreonService
from app.services.user_service import UserService

router = APIRouter(tags=["hub"])


def _require_admin_token(x_admin_token: str) -> None:
    settings = get_settings()
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def _activate_internal(
    payload: ActivateRequest,
    x_user_token: str,
    db: Session,
):
    service = LicenseService(db)
    ok, message, record = service.activate_key(payload.key, payload.hwid)
    if not record:
        raise HTTPException(status_code=404, detail=message)

    if ok and x_user_token:
        user_service = UserService(db)
        user = user_service.get_user_by_token(x_user_token)
        if user:
            user_service.link_license_to_user(user.id, record.id)

    return {
        "success": ok,
        "message": message,
        "status": record.status.value,
        "expires_at": record.expires_at,
    }


def _validate_internal(payload: ValidateRequest, db: Session, x_user_token: str = "") -> ValidateResponse:
    service = LicenseService(db)
    valid, message, record, seconds_left = service.validate_key(payload.key, payload.hwid)
    if not record:
        return ValidateResponse(
            valid=False,
            status="invalid",
            expires_at=None,
            message=message,
            seconds_left=None,
            temporary_license=False,
        )

    if valid and x_user_token:
        user_service = UserService(db)
        user = user_service.get_user_by_token(x_user_token)
        if user:
            user_service.link_license_to_user(user.id, record.id)

    return ValidateResponse(
        valid=valid,
        status=record.status.value,
        expires_at=record.expires_at,
        message=message,
        seconds_left=seconds_left,
        temporary_license=record.temporary_from_patreon,
    )


@router.post("/hub/generate_key", response_model=GenerateKeyResponse)
def generate_key(
    payload: GenerateKeyRequest,
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(x_admin_token)

    service = LicenseService(db)
    key, record = service.generate_key(
        duration_value=payload.duration,
        patreon_user_id=payload.patreon_user_id,
        notes=payload.notes,
    )
    return GenerateKeyResponse(
        key=key,
        duration=record.duration.value,
        expires_at=record.expires_at,
        status=record.status.value,
    )


@router.post("/generate_key", response_model=GenerateKeyResponse, include_in_schema=False)
def generate_key_legacy(
    payload: GenerateKeyRequest,
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    return generate_key(payload=payload, x_admin_token=x_admin_token, db=db)


@router.post("/hub/activate", response_model=ActivateResponse)
def activate_key(
    payload: ActivateRequest,
    x_user_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    return _activate_internal(payload=payload, x_user_token=x_user_token, db=db)


@router.post("/activate", response_model=ActivateResponse, include_in_schema=False)
def activate_key_legacy(
    payload: ActivateRequest,
    x_user_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    return _activate_internal(payload=payload, x_user_token=x_user_token, db=db)


@router.post("/hub/validate", response_model=ValidateResponse)
def validate_key(
    payload: ValidateRequest,
    x_user_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    return _validate_internal(payload=payload, db=db, x_user_token=x_user_token)


@router.get("/validate", response_model=ValidateResponse, include_in_schema=False)
def validate_key_legacy(
    key: str = Query(...),
    hwid: str = Query(...),
    x_user_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    return _validate_internal(payload=ValidateRequest(key=key, hwid=hwid), db=db, x_user_token=x_user_token)


@router.get("/patreon_auth", response_model=PatreonAuthResponse)
async def patreon_auth(
    patreon_access_token: str = Query(..., description="OAuth access token"),
    hwid: str = Query(default=""),
    db: Session = Depends(get_db),
):
    patreon = PatreonService(db)
    result = await patreon.verify_subscription(patreon_access_token)
    if not result.is_active:
        return PatreonAuthResponse(
            patreon_active=False,
            patreon_user_id=result.patreon_user_id,
            generated_key=None,
            expires_at=None,
            message=result.message,
        )

    service = LicenseService(db)
    key, record = service.generate_key(
        duration_value="temporary",
        patreon_user_id=result.patreon_user_id,
        notes="Auto-generated from Patreon subscription",
        temporary=True,
    )
    return PatreonAuthResponse(
        patreon_active=True,
        patreon_user_id=result.patreon_user_id,
        generated_key=key,
        expires_at=record.expires_at,
        message="Temporary license generated from Patreon subscription. Activate the key to bind HWID.",
    )


@router.post("/hub/license/{license_id}/extend", response_model=HubActionResponse)
def hub_extend_license(
    license_id: str,
    payload: ExtendLicenseRequest,
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(x_admin_token)
    service = LicenseService(db)
    record = service.extend_license(license_id=license_id, add_value=payload.add)
    if not record:
        raise HTTPException(status_code=404, detail="License not found.")
    return HubActionResponse(success=True, message="License extended.", status=record.status.value)


@router.post("/hub/license/{license_id}/revoke", response_model=HubActionResponse)
def hub_revoke_license(
    license_id: str,
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(x_admin_token)
    service = LicenseService(db)
    record = service.revoke_license(license_id=license_id)
    if not record:
        raise HTTPException(status_code=404, detail="License not found.")
    return HubActionResponse(success=True, message="License revoked.", status=record.status.value)


@router.delete("/hub/license/{license_id}", response_model=HubActionResponse)
def hub_delete_license(
    license_id: str,
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(x_admin_token)
    service = LicenseService(db)
    deleted = service.delete_license(license_id=license_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="License not found.")
    return HubActionResponse(success=True, message="License deleted.", status="deleted")
