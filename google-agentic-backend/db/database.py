from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from configs.config import get_settings
from sqlalchemy import text

settings = get_settings()
DATABASE_URL = settings.database.postgres_connection_string.get_secret_value()

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_size=20,         
    max_overflow=20,      
    pool_timeout=60,      
    pool_recycle=3600
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_db_connection():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")) 
        print("✅ Successfully connected to the database!")
    except OperationalError as e:
        print("❌ Failed to connect to the database.")
        print(f"Error: {e}")

# Run the check
check_db_connection()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
