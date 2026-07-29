"""Configuração do banco de dados SQLite e sessão SQLAlchemy."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# O filesystem da Vercel é somente leitura; /tmp é gravável durante a execução.
if os.getenv("VERCEL"):
    # A imagem Linux da Vercel só permite escrita em /tmp. Criamos a pasta
    # explicitamente para que o SQLite possa abrir o arquivo desde o startup.
    try:
        Path("/tmp").mkdir(parents=True, exist_ok=True)
    except OSError:
        # Em um computador Windows com VERCEL definido manualmente, /tmp pode
        # não existir. Na Vercel (Linux), o diretório já é gravável.
        pass
    DATABASE_URL = "sqlite:////tmp/relatorios.db"
else:
    DATABASE_URL = "sqlite:///./relatorios.db"

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
