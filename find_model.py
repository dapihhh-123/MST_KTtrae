
import sys
import os
import inspect

sys.path.append(os.getcwd())

try:
    from backend import models
    print(f"models module: {models}")
    print(f"models file: {models.__file__}")
    
    if hasattr(models, 'OracleTaskVersion'):
        print("OracleTaskVersion found in models")
        klass = models.OracleTaskVersion
        print(f"Defined in: {inspect.getfile(klass)}")
    else:
        print("OracleTaskVersion NOT found in models")
        # List all attributes
        print(dir(models))
        
except Exception as e:
    print(f"Error: {e}")
