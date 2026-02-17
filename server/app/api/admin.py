from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.session import get_db
from app.services.license_service import LicenseService
from app.services.update_service import UpdateService
from app.services.user_service import UserService

router = APIRouter(tags=["admin"], include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


def _require_admin_token(admin_token: str, x_admin_token: str) -> None:
    settings = get_settings()
    provided_token = x_admin_token or admin_token
    if provided_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    generated_key: str = Query(default=""),
    generated_license_id: str = Query(default=""),
    update_notice_sent: str = Query(default=""),
    update_version: str = Query(default=""),
    db: Session = Depends(get_db),
):
    license_service = LicenseService(db)
    user_service = UserService(db)
    records = license_service.list_licenses(limit=300)
    owner_map = user_service.get_license_owner_map([item.id for item in records])
    users = user_service.list_users(limit=100)
    user_summary = user_service.build_user_license_summary(users)
    active_count = sum(1 for item in records if item.status.value == "active")
    inactive_count = len(records) - active_count
    update_info = UpdateService().latest()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "licenses": records,
            "app_name": get_settings().app_name,
            "active_count": active_count,
            "inactive_count": inactive_count,
            "users": user_summary,
            "user_count": len(users),
            "owner_map": owner_map,
            "generated_key": generated_key,
            "generated_license_id": generated_license_id,
            "update_notice_sent": update_notice_sent,
            "update_version": update_version,
            "update_info": update_info,
        },
    )


@router.get("/admin/keys", response_class=HTMLResponse)
def admin_all_keys(
    request: Request,
    status: str = Query(default="all"),
    q: str = Query(default=""),
    db: Session = Depends(get_db),
):
    service = LicenseService(db)
    user_service = UserService(db)
    records = service.list_licenses(limit=5000)

    status = status.lower().strip()
    q = q.strip().lower()

    if status != "all":
        records = [item for item in records if item.status.value == status]

    if q:
        records = [
            item
            for item in records
            if q in item.display_key.lower()
            or (item.full_key and q in item.full_key.lower())
            or q in item.id.lower()
            or (item.patreon_user_id and q in item.patreon_user_id.lower())
            or (item.notes and q in item.notes.lower())
        ]

    owner_map = user_service.get_license_owner_map([item.id for item in records])

    active_count = sum(1 for item in records if item.status.value == "active")
    inactive_count = len(records) - active_count

    return templates.TemplateResponse(
        request=request,
        name="keys.html",
        context={
            "licenses": records,
            "active_count": active_count,
            "inactive_count": inactive_count,
            "total_count": len(records),
            "selected_status": status,
            "search_q": q,
            "app_name": get_settings().app_name,
            "owner_map": owner_map,
        },
    )


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    q: str = Query(default=""),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    users = service.list_users(limit=1000, q=q)
    summary = service.build_user_license_summary(users)
    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "app_name": get_settings().app_name,
            "users": summary,
            "search_q": q,
            "total_count": len(summary),
        },
    )


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
def admin_user_detail(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    licenses = service.get_user_licenses(user_id)
    return templates.TemplateResponse(
        request=request,
        name="admin_user_detail.html",
        context={
            "app_name": get_settings().app_name,
            "user": user,
            "licenses": licenses,
        },
    )


@router.get("/admin/licenses/{license_id}", response_class=HTMLResponse)
def admin_license_detail(
    license_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    license_service = LicenseService(db)
    user_service = UserService(db)
    record = license_service.get_license_by_id(license_id)
    if not record:
        raise HTTPException(status_code=404, detail="License not found.")
    owner = user_service.get_license_owner_map([license_id]).get(license_id)
    return templates.TemplateResponse(
        request=request,
        name="admin_license_detail.html",
        context={
            "app_name": get_settings().app_name,
            "license": record,
            "owner": owner,
        },
    )


@router.post("/admin/generate")
def admin_generate(
    duration: str = Form(...),
    patreon_user_id: str = Form(default=""),
    notes: str = Form(default=""),
    admin_token: str = Form(default=""),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)

    service = LicenseService(db)
    raw_key, record = service.generate_key(
        duration_value=duration,
        patreon_user_id=patreon_user_id or None,
        notes=notes or None,
    )
    return RedirectResponse(
        url=f"/admin?generated_key={raw_key}&generated_license_id={record.id}",
        status_code=303,
    )


@router.post("/admin/update/notify")
def admin_notify_update(
    admin_token: str = Form(default=""),
    message: str = Form(default=""),
    x_admin_token: str = Header(default=""),
):
    _require_admin_token(admin_token, x_admin_token)
    latest = UpdateService().trigger_update_notification(message=message)
    version = latest.get("version", "unknown")
    return RedirectResponse(url=f"/admin?update_notice_sent=1&update_version={version}", status_code=303)


@router.post("/admin/license/{license_id}/extend")
def admin_extend_license(
    license_id: str,
    add: str = Form(...),
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/keys"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = LicenseService(db)
    service.extend_license(license_id=license_id, add_value=add)
    return RedirectResponse(url=next_url or "/admin/keys", status_code=303)


@router.post("/admin/license/{license_id}/revoke")
def admin_revoke_license(
    license_id: str,
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/keys"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = LicenseService(db)
    service.revoke_license(license_id=license_id)
    return RedirectResponse(url=next_url or "/admin/keys", status_code=303)


@router.post("/admin/license/{license_id}/deactivate")
def admin_deactivate_license(
    license_id: str,
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/keys"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = LicenseService(db)
    service.revoke_license(license_id=license_id)
    return RedirectResponse(url=next_url or "/admin/keys", status_code=303)


@router.post("/admin/license/{license_id}/reactivate")
def admin_reactivate_license(
    license_id: str,
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/keys"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = LicenseService(db)
    service.reactivate_license(license_id=license_id)
    return RedirectResponse(url=next_url or "/admin/keys", status_code=303)


@router.post("/admin/license/{license_id}/delete")
def admin_delete_license(
    license_id: str,
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/keys"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = LicenseService(db)
    service.delete_license(license_id=license_id)
    return RedirectResponse(url=next_url or "/admin/keys", status_code=303)


@router.post("/admin/users/{user_id}/disable")
def admin_disable_user(
    user_id: str,
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/users"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = UserService(db)
    service.disable_user(user_id)
    return RedirectResponse(url=next_url or "/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def admin_delete_user(
    user_id: str,
    revoke_licenses: str = Form(default="0"),
    admin_token: str = Form(default=""),
    next_url: str = Form(default="/admin/users"),
    x_admin_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    _require_admin_token(admin_token, x_admin_token)
    service = UserService(db)
    service.delete_user(user_id=user_id, revoke_linked_licenses=revoke_licenses == "1")
    return RedirectResponse(url=next_url or "/admin/users", status_code=303)
