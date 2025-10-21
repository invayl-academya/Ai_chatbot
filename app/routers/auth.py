# backend/app/routers/auth.py
from datetime import timedelta, datetime, timezone
from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query , Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from fastapi.security import   OAuth2PasswordRequestForm , OAuth2PasswordBearer
from jose import jwt, JWTError

from ..database import get_db
from ..models import Users  # <-- singular, must match models.py


from passlib.context import  CryptContext

authRoutes = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET  = "efg983r639yr5sd8e5eljkf78e0trubsaet4er34terg4t4f3r3r4g4r3r45gfer4t325t"
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")
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

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: int
    name: Optional[str]
    email: EmailStr
    username: Optional[str]
    role: str

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


def create_access_token(email :EmailStr , user_id :int , expires_delta :Optional[timedelta] = None) :
    to_encode = {"sub" : email , "uid" :user_id}
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp" :expire  })
    return  jwt.encode( to_encode , JWT_SECRET , algorithm=ALGORITHM)


def get_current_user  ( token :Annotated[str , Depends(oauth2_bearer) ] , db:db_link) :
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email = payload.get("sub")
        user_id = payload.get("uid")
        if not email or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authorized: missing claims",
            )
        user = db.query(Users).get(user_id)  # or filter by email if you prefer
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")



def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt_context.verify(plain, hashed)

@authRoutes.post("/login" , response_model=TokenResponse)
async def login(payload: LoginRequest, db: db_link , response :Response):
    user = db.query(Users).filter(Users.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(email=user.email, user_id=user.id)

    # DEV: localhost can use secure=False and samesite="lax"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60,      # 1 hour
        expires=60 * 60,
        samesite="lax",       # use "none" + secure=True when on HTTPS cross-site
        secure=False,         # set True in production (HTTPS)
    )


    return TokenResponse(
            access_token=token,
            id=user.id,
            name=user.name,
            email=user.email,
            username=user.username,
            role=user.role,
        )

@authRoutes.get("/me", response_model=UserOut)
def read_me(current_user: Annotated[Users, Depends(get_current_user)]):
    return current_user
    
