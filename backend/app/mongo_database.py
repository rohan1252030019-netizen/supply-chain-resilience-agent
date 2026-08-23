"""
app/mongo_database.py
Owner: Developer 2 (Backend / Simulation)

MongoDB connection setup using PyMongo.
Uses MongoDB Atlas (or local) depending on MONGO_URI in .env.
"""

from pymongo import MongoClient
from app.config import settings

client = MongoClient(
    settings.MONGO_URI,
    serverSelectionTimeoutMS=2000,
    connectTimeoutMS=2000,
    socketTimeoutMS=5000,
    maxPoolSize=50,
    minPoolSize=5,
    maxIdleTimeMS=45000,
    tlsAllowInvalidCertificates=True,
    retryWrites=True,
)
db = client[settings.MONGO_DB_NAME]


def get_mongo_db():
    """FastAPI dependency — returns the active database handle."""
    return db


def ping_mongo() -> None:
    """Called at startup to confirm Atlas connectivity."""
    try:
        client.admin.command("ping")
        print(f"[MongoDB] Connected to '{settings.MONGO_DB_NAME}' via Atlas.")
    except Exception as e:
        print(f"[MongoDB] WARNING: could not ping MongoDB: {e}")
        # Non-fatal: allow startup so health endpoint still works
