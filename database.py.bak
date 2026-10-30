import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bookings.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class BookingRecord(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    guests = Column(Integer)
    details = Column(Text)
    status = Column(String, default="pending")
    customer_response = Column(String, default="not_sent")
    rule_warnings = Column(Text)
    high_demand_note = Column(Text)
    calendar_link = Column(Text)
    calendar_event_id = Column(String)
    reminder_sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_columns()


def migrate_sqlite_columns():
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.connect() as conn:
        existing_columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(bookings)").fetchall()]

        if "customer_response" not in existing_columns:
            conn.exec_driver_sql("ALTER TABLE bookings ADD COLUMN customer_response VARCHAR DEFAULT 'not_sent'")

        if "high_demand_note" not in existing_columns:
            conn.exec_driver_sql("ALTER TABLE bookings ADD COLUMN high_demand_note TEXT")

        if "reminder_sent_at" not in existing_columns:
            conn.exec_driver_sql("ALTER TABLE bookings ADD COLUMN reminder_sent_at DATETIME")

        conn.commit()