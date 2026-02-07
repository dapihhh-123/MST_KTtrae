
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional, Union

class Signature(BaseModel):
    function_name: str = "solve"
    args: List[str] = []
    returns: str = "Any"

class PublicExample(BaseModel):
    name: str
    input: Union[Dict[str, Any], Any]
    expected: Any
    explanation: Optional[str] = None

class TaskSpec(BaseModel):
    goal_one_liner: str = Field(default="")
    deliverable: str = "function"
    language: str = "python"
    runtime: str = "python"
    signature: Optional[Signature] = None
    constraints: List[str] = []
    assumptions: List[str] = []
    output_ops: List[str] = []
    output_shape: Dict[str, Any] = {}
    ambiguities: List[Dict[str, Any]] = []
    public_examples: List[PublicExample] = []
    confidence_reasons: List[str] = []

    @model_validator(mode='after')
    def apply_defaults(self):
        # P4-1: Default values and auto-completion
        if self.deliverable == "cli":
            if not self.signature:
                self.signature = Signature(function_name="main", args=[], returns="int")
        elif self.deliverable == "function":
            if not self.signature:
                # Default for generic function tasks
                self.signature = Signature(function_name="solve", args=["ops"], returns="list")
            
            # P4-3: Lock return type if explicit mismatch risk
            # If function name implies boolean (is_*, has_*, check_*), force bool
            if self.signature and self.signature.function_name:
                fname = self.signature.function_name.lower()
                if fname.startswith("is_") or fname.startswith("has_") or fname.startswith("check_"):
                    if self.signature.returns == "Any":
                        self.signature.returns = "bool"
        
        return self

class HiddenTest(BaseModel):
    name: str
    input: Union[Dict[str, Any], Any]
    expected: Any
    tags: List[str] = []
    weight: float = 1.0

class GeneratedTests(BaseModel):
    public_examples: List[PublicExample]
    hidden_tests: List[HiddenTest]
