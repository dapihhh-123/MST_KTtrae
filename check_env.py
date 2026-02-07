
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    from backend import models
    print("Models imported.")
    if hasattr(models, 'OracleTask'):
        print("OracleTask found in models.")
    else:
        print("OracleTask NOT found in models.")
        print("Available attributes in models:", dir(models))
except ImportError as e:
    print(f"Failed to import models: {e}")

try:
    from backend.services.oracle import mock_llm
    print("mock_llm imported.")
except ImportError as e:
    print(f"Failed to import mock_llm: {e}")

try:
    from backend.routers import oracle
    print("routers.oracle imported.")
except ImportError as e:
    print(f"Failed to import routers.oracle: {e}")
