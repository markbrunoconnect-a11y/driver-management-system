from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.core.security import hash_password, verify_password, create_token, get_current_user, require_admin
from app import models

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CreateUserRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "driver"
    is_vehicle_manager: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    is_vehicle_manager: bool | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/bootstrap", status_code=201)
def bootstrap(req: CreateUserRequest, db: Session = Depends(get_db)):
    """Create the first admin — only works on empty database."""
    if db.query(models.User).count() > 0:
        raise HTTPException(status_code=400, detail="Bootstrap only allowed on empty database")
    user = models.User(
        name=req.name,
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        role=models.UserRole.admin,
        is_vehicle_manager=False,
    )
    db.add(user)
    db.commit()
    return {"message": "Admin account created"}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.email == req.email.lower(),
        models.User.is_active == True
    ).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "token": create_token(user.id),
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "is_vehicle_manager": user.is_vehicle_manager,
    }


@router.get("/me")
def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_vehicle_manager": current_user.is_vehicle_manager,
    }


@router.post("/users", status_code=201)
def create_user(req: CreateUserRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    if req.role not in ("admin", "dispatcher", "driver"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if db.query(models.User).filter(models.User.email == req.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    # Only one vehicle manager at a time
    if req.is_vehicle_manager:
        existing_vm = db.query(models.User).filter(models.User.is_vehicle_manager == True).first()
        if existing_vm:
            existing_vm.is_vehicle_manager = False
    user = models.User(
        name=req.name,
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        role=models.UserRole(req.role),
        is_vehicle_manager=req.is_vehicle_manager,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    users = db.query(models.User).order_by(models.User.name).all()
    return [_user_out(u) for u in users]


@router.patch("/users/{user_id}")
def update_user(user_id: int, req: UpdateUserRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.name is not None:
        user.name = req.name
    if req.role is not None:
        user.role = models.UserRole(req.role)
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.is_vehicle_manager is not None:
        # Remove vehicle manager from previous holder
        if req.is_vehicle_manager:
            prev = db.query(models.User).filter(
                models.User.is_vehicle_manager == True,
                models.User.id != user_id
            ).first()
            if prev:
                prev.is_vehicle_manager = False
        user.is_vehicle_manager = req.is_vehicle_manager
    db.commit()
    return _user_out(user)


@router.patch("/users/{user_id}/reset-password")
def reset_password(user_id: int, req: ResetPasswordRequest, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password reset"}


def _user_out(u):
    return {
        "id": u.id, "name": u.name, "email": u.email,
        "role": u.role, "is_vehicle_manager": u.is_vehicle_manager,
        "is_active": u.is_active,
    }
