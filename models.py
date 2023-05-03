import os
import uuid

from sqlalchemy import Column, Integer, String, DateTime, Text, func, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy_utils import UUIDType
from load_dotenv import load_dotenv

load_dotenv()

POSTGRES_USER=os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD=os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB=os.getenv('POSTGRES_DB')
DB_PORT=os.getenv('DB_PORT')
DB_HOST=os.getenv('DB_HOST')


engine = create_async_engine(f'postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}')
Base = declarative_base(bind=engine)


class User(Base):

    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    advs = relationship('Advertisement', backref='user', lazy='joined')

    def __repr__(self):
        return f'<user {self.id}>'


class Advertisement(Base):

    __tablename__ = 'advertisements'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    user_id = Column(Integer, ForeignKey(User.id))

    def __repr__(self):
        return f'<{self.title}>'


class Token(Base):

    __tablename__ = 'tokens'

    id = Column(UUIDType, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, server_default=func.now())
    user_id = Column(Integer, ForeignKey(User.id))
    user = relationship(User, backref='token', lazy='joined')
