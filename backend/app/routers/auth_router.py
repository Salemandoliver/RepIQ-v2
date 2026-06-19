from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import (verify_password, create_token, get_current_user, hash_password,
                    validate_new_password)
from ..db import get_db
from ..models import User
from ..schemas import (LoginRequest, TokenResponse, UserOut, ChangePasswordRequest,
                       SetPasswordRequest)
from ..services.salesiq.roles import role_for_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(db: Session, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.sales_role = role_for_user(db, user)
    # Enrich with the signed-in user's HR display identity (preferred name + photo), if set.
    # Wrapped so a missing/not-yet-created HR table never breaks auth.
    try:
        from ..modules.hr.models import Employee, EmployeePersonal
        pers = (db.query(EmployeePersonal)
                .join(Employee, EmployeePersonal.employee_id == Employee.id)
                .filter(Employee.user_id == user.id, EmployeePersonal.deleted_at.is_(None))
                .first())
        if pers:
            out.preferred_name = pers.preferred_name
            out.photo = pers.profile_photo
    except Exception:
        pass
    return out


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.active:
        raise HTTPException(403, "Account is deactivated")
    user.last_login_at = datetime.utcnow()
    db.commit()
    return TokenResponse(access_token=create_token(user), user=_user_out(db, user))


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _user_out(db, user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(body: ChangePasswordRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Signed-in user changes their own password (current password required, new entered twice)."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    validate_new_password(body.new_password, body.confirm_password)
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(400, "Please choose a password different from your current one")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.utcnow()
    user.must_set_password = False
    db.commit()
    db.refresh(user)
    # Re-issue a token so the current session keeps working (older tokens are now invalidated).
    return TokenResponse(access_token=create_token(user), user=_user_out(db, user))


def _setup_user(db: Session, token: str) -> User:
    token = (token or "").strip()
    user = db.query(User).filter(User.reset_token == token).first() if token else None
    if not user:
        raise HTTPException(404, "This link is invalid. Ask your manager to send a new one.")
    if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
        raise HTTPException(410, "This link has expired. Ask your manager to send a new one.")
    if not user.active and not user.must_set_password:
        raise HTTPException(403, "This account is no longer active.")
    return user


@router.get("/setup/{token}")
def setup_info(token: str, db: Session = Depends(get_db)):
    """Public: validate an invite/reset link and return whom it's for, so the set-password
    page can greet them and show the right wording."""
    user = _setup_user(db, token)
    return {"name": user.name, "email": user.email,
            "mode": "invite" if user.must_set_password else "reset"}


@router.post("/setup/{token}", response_model=TokenResponse)
def setup_set_password(token: str, body: SetPasswordRequest, db: Session = Depends(get_db)):
    """Public: a user sets their password from an invite/reset link (entered twice), then is
    signed straight in."""
    user = _setup_user(db, token)
    validate_new_password(body.new_password, body.confirm_password)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.utcnow()
    user.must_set_password = False
    user.active = True
    user.reset_token = None
    user.reset_token_expires = None
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_token(user), user=_user_out(db, user))
