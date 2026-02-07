
import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

try:
    from backend.services.oracle.types import TaskSpec, Signature
    from backend.routers.oracle import SpecBody
    
    print("=== Pydantic Model Inspection ===")
    
    print("\n[TaskSpec Fields]")
    for name, field in TaskSpec.model_fields.items():
        default = field.default
        print(f"  {name}: default={default}")
        
    print("\n[Signature Fields]")
    for name, field in Signature.model_fields.items():
        default = field.default
        print(f"  {name}: default={default}")

    print("\n[SpecBody Fields]")
    for name, field in SpecBody.model_fields.items():
         default = field.default
         print(f"  {name}: default={default}")

except Exception as e:
    print(f"Error inspecting models: {e}")
