import sys
import os

# Add backend directory to path so app modules can be resolved on serverless platforms
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app
