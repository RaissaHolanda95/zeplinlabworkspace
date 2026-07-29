"""Configuração do banco de dados SQLite e sessão SQLAlchemy."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# O filesystem da Vercel é somente leitura; /tmp é gravável durante a execução.
DATABASE_URL = "sqlite:////tmp/relatorios.db" if os.getenv("VERCEL") else "sqlite:///./relatorios.db"

# O SQLite requer esta opção quando a aplicação atende requisições em mais de uma thread.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe base para todos os modelos ORM."""


def get_db():
    """Fornece uma sessão por requisição para dependências do FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
