from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# URL de votre base de données Supabase PostgreSQL
DATABASE_URL = "postgresql://postgres.puaqtxuwoqwaozzgkcqo:automaticerclavie@aws-0-eu-west-2.pooler.supabase.com:6543/postgres"

# Note : connect_args a été retiré car il est spécifique à SQLite
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
