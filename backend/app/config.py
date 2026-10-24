import os
from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development")
DATA_DIR = os.getenv("DATA_DIR", "./data")
METADATA_DB = os.getenv("METADATA_DB", "./data/app_metadata.sqlite")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "approved-local-model")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_QUERY_SECONDS = float(os.getenv("MAX_QUERY_SECONDS", "5"))
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "500"))
MAX_RESULT_BYTES = int(os.getenv("MAX_RESULT_BYTES", "2000000"))
MAX_REPAIR_ATTEMPTS = int(os.getenv("MAX_REPAIR_ATTEMPTS", "2"))