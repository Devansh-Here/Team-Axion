import os
from app.model_client import ModelClient

name = os.environ.get("MODEL_NAME", "qwen2.5-coder:1.5b")
c = ModelClient(model=name)
print("model:", name)
print("available:", c.is_available())
print("reply:", c.generate('Reply with JSON {"ok": true}'))