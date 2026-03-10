from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class InventoryItem(Base):
    __tablename__ = 'inventory'

    id          = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False)
    days_until_spoil = Column(Float, nullable=False)
    added_on    = Column(DateTime, default=datetime.utcnow)
    expires_on  = Column(DateTime, nullable=False)

# Create database and tables
engine = create_engine('sqlite:///snapchef.db')
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

def get_session():
    return Session()