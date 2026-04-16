# Copied from crypto/india-le-platform/backend/app/utils/auth.py
# at commit 9e7d7b8 on 2026-04-16.
# Sync via tools/sync-from-crypto.sh. If you need to change behaviour,
# change upstream first if possible.
# Local changes (if any) documented at the bottom of CRYPTO_SYNC.md.

"""Authentication utilities."""
# PLATFORM — Safe to copy to sibling LEA-forensic-platform projects.
# Domain-agnostic. Do NOT add imports from services/fetchers/*,
# analysis/dex_decoder.py, analysis/privacy_chains.py, or any other
# crypto-specific module. See PLATFORM_MODULES.md at repo root.
# Cross-project consumers: ping Saurabh / #platform-sync on interface changes.

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings

# Password hashing context
# pbkdf2_sha256 only — bcrypt removed because passlib+bcrypt version mismatch on
# Railway causes "password cannot be longer than 72 bytes" ValueError on verify.
# All production hashes use pbkdf2_sha256. If a bcrypt hash somehow exists in DB,
# passlib will reject it cleanly (unrecognized scheme) instead of crashing.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.effective_jwt_secret, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, settings.effective_jwt_secret, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency to get current authenticated user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
        
    # In a real app, strict check: user = db.query(User).filter...
    # For now, return the payload info
    return {"username": username, "sub": username, "role": payload.get("role", "officer")}
