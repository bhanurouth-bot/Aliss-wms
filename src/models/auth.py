# src/models/auth.py
from sqlalchemy import Column, Integer, String, Boolean
from src.core.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    # 'Admin', 'Warehouse Staff', 'Production Manager', 'Purchasing'
    role = Column(String, default="Warehouse Staff") 
    is_active = Column(Boolean, default=True)