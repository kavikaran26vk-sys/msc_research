import os
from sqlalchemy import create_engine, Column, String, Float, Integer, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

DB_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

engine = SessionLocal = Base = None

def init_db():
    global engine, SessionLocal, Base
    engine = create_engine(DB_URL)
    SessionLocal = sessionmaker(bind=engine)
    Base = declarative_base()
    return engine, SessionLocal, Base

engine, SessionLocal, Base = init_db()

class Cluster(Base):
    __tablename__ = "clusters"
    cluster_id      = Column(String, primary_key=True)
    product_count   = Column(Integer)
    retailer_count  = Column(Integer)
    retailers       = Column(String)
    best_price      = Column(Float)
    best_retailer   = Column(String)
    products        = relationship("Product", back_populates="cluster")

class Product(Base):
    __tablename__ = "products"
    global_id    = Column(String, primary_key=True)
    cluster_id   = Column(String, ForeignKey("clusters.cluster_id"))
    retailer     = Column(String)
    name         = Column(Text)
    brand        = Column(String)
    price        = Column(Float)
    price_str    = Column(String)
    ram          = Column(String)
    storage      = Column(String)
    screen_size  = Column(String)
    processor    = Column(String)
    gpu          = Column(String)
    url          = Column(Text)
    stock_status = Column(String)
    cluster      = relationship("Cluster", back_populates="products")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()