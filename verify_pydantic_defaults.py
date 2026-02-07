
from backend.services.oracle.types import TaskSpec, Signature

def test_defaults():
    print("Testing Pydantic Defaults...")
    
    # Case 1: CLI Default
    s1 = TaskSpec(goal_one_liner="test", deliverable="cli")
    print(f"Case 1 (CLI): {s1.signature}")
    assert s1.signature.function_name == "main"
    assert s1.signature.returns == "int"
    
    # Case 2: Function Default
    s2 = TaskSpec(goal_one_liner="test", deliverable="function")
    print(f"Case 2 (Function): {s2.signature}")
    assert s2.signature.function_name == "solve"
    assert s2.signature.returns == "list" # My default
    
    # Case 3: Explicit Signature
    s3 = TaskSpec(goal_one_liner="test", deliverable="function", signature=Signature(function_name="foo", returns="bar"))
    print(f"Case 3 (Explicit): {s3.signature}")
    assert s3.signature.function_name == "foo"
    assert s3.signature.returns == "bar"

    print("All defaults verified!")

if __name__ == "__main__":
    try:
        test_defaults()
    except Exception as e:
        print(f"FAILED: {e}")
