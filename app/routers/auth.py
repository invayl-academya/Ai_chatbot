# backend/app/routers/auth.py
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session


from ..database import get_db
from ..models import Users  # <-- singular, must match models.py


from passlib.context import  CryptContext

authRoutes = APIRouter(prefix="/auth", tags=["auth"])

db_link = Annotated[Session, Depends(get_db)]




bcrypt_context = CryptContext(schemes=['bcrypt'] , deprecated='auto')


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt_context.verify(plain, hashed)  # <-- use the same context

class UserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str = "student"
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=6, max_length=120)

class UserOut(BaseModel):
    id: int
    name: Optional[str]
    email: EmailStr
    username: Optional[str]
    role: str
    is_active: bool
    class Config:
        from_attributes = True  # Pydantic v2

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@authRoutes.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRequest, db: db_link):
    email = payload.email.strip().lower()
    username = payload.username.strip()

    # Optional duplicate checks (recommended)
    existing = (
        db.query(Users)
        .filter((Users.email == email) | (Users.username == username))
        .first()
    )
    if existing:
        if existing.email == email:
            raise HTTPException(status_code=409, detail="Email already registered")
        if existing.username == username:
            raise HTTPException(status_code=409, detail="Username already taken")
        raise HTTPException(status_code=409, detail="User already exists")

    user = Users(
        name=payload.name,
        email=email,
        username=username,
        role=payload.role,
        hashed_password=bcrypt_context.hash(payload.password),  # TEMP: will hash later
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user



@authRoutes.get("/users", response_model=List[UserOut])
def list_users(
    db: db_link,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    users = (
        db.query(Users)
        .order_by(Users.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return users


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt_context.verify(plain, hashed)

@authRoutes.post("/login")
def login(payload: LoginRequest, db: db_link):
    user = db.query(Users).filter(Users.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"ok": True, "user_id": user.id}
