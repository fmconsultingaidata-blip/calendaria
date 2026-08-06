from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite pour aller vite en POC. À remplacer par une URL Postgres
# (postgresql://user:pass@host/db) quand on passera en prod ;
# le schéma SQLAlchemy ci-dessous reste compatible.
DATABASE_URL = "sqlite:///./poc_planning.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
