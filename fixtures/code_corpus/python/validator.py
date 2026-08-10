from pydantic import BaseModel, validator, EmailStr
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    """Schema for user creation."""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    
    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserUpdate(BaseModel):
    """Schema for user updates."""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

class DocumentCreate(BaseModel):
    """Schema for document creation."""
    title: str
    content: str
    tags: Optional[List[str]] = []
    
    @validator('title')
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Title cannot be empty')
        return v
    
    @validator('content')
    def content_min_length(cls, v):
        if len(v) < 10:
            raise ValueError('Content must be at least 10 characters')
        return v
