
import subprocess
import json
import logging
import os
import tempfile
import sys
import pathlib
import traceback

logger = logging.getLogger("Backend")

def default_resource_limits(timeout_sec: float):
    return {"timeout_sec": timeout_sec, "memory_mb": 128}

def default_sandbox_mode():
    return "local"

def load_code_text(db, code_snapshot_id, code_text):
    if code_text: return code_text
    return ""

def setup_workspace(temp_dir: str, workspace_files: dict):
    if not workspace_files:
        return
    for path, content in workspace_files.items():
        # Prevent path traversal
        clean_path = os.path.normpath(path)
        if clean_path.startswith("..") or os.path.isabs(clean_path):
            continue
            
        full_path = pathlib.Path(temp_dir) / clean_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

def run_function_oracle(db, code_text, function_name, tests, timeout_sec, stdout_max_bytes, stderr_max_bytes, sandbox_mode, resource_limits, workspace_files=None, entrypoint=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        module_name = "main"
        
        # Setup Workspace
        if workspace_files:
            setup_workspace(temp_dir, workspace_files)
            if entrypoint:
                # Convert "src/main.py" -> "src.main"
                # Strip extension
                base = os.path.splitext(entrypoint)[0]
                module_name = base.replace("/", ".").replace("\\", ".")
        else:
            # Legacy Single File Mode
            with open(os.path.join(temp_dir, "main.py"), "w", encoding="utf-8") as f:
                f.write(code_text or "")
        
        # Create Runner Script
        runner_script_path = os.path.join(temp_dir, "__runner__.py")
        
        runner_code = f"""
import json
import sys
import os
import traceback
import importlib

# Add current dir to sys.path so we can import user modules
sys.path.insert(0, os.getcwd())

# 1. Import User Module
try:
    user_module = importlib.import_module("{module_name}")
except Exception as e:
    print(json.dumps({{"passed": 0, "failed": 0, "failures": [{{"test_name": "__import__", "error": f"Import Failed: {{str(e)}}\\n{{traceback.format_exc()}}"}}]}}))
    sys.exit(0)

# 2. Get Target Function
try:
    target_func = getattr(user_module, "{function_name}")
except AttributeError:
    print(json.dumps({{"passed": 0, "failed": 0, "failures": [{{"test_name": "__init__", "error": "Function '{function_name}' not found in module '{module_name}'"}}]}}))
    sys.exit(0)

# 3. Load Tests
try:
    raw_tests_json = r'''{json.dumps(tests)}'''
    tests = json.loads(raw_tests_json)
except Exception as e:
    print(json.dumps({{"passed": 0, "failed": 0, "failures": [{{"test_name": "__runner_init__", "error": f"JSON Parse Failed: {{str(e)}}"}}]}}))
    sys.exit(0)

results = {{"passed": 0, "failed": 0, "failures": []}}

# 4. Run Tests
for t in tests:
    try:
        inp = t["input"]
        expected = t["expected"]
        
        # Contract Enforcement
        if isinstance(inp, list):
            args = inp
        else:
            args = [inp]
             
        try:
            got = target_func(*args)
        except Exception as e:
            got = None
            raise e
            
        # Comparison Logic
        match = False
        try:
            if got == expected:
                match = True
            elif isinstance(got, (list, tuple)) and isinstance(expected, (list, tuple)):
                match = list(got) == list(expected)
        except:
            match = False
            
        if match:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["failures"].append({{
                "test_name": t["name"],
                "input": inp,
                "expected": expected,
                "got": got,
                "error": None
            }})
    except Exception as e:
        results["failed"] += 1
        results["failures"].append({{
            "test_name": t["name"],
            "input": t.get("input"),
            "expected": t.get("expected"),
            "got": None,
            "error": f"{{str(e)}}\\n{{traceback.format_exc()}}"
        }})

print(json.dumps(results))
"""
        with open(runner_script_path, "w", encoding="utf-8") as f:
            f.write(runner_code)
            
        try:
            res = subprocess.run(
                [sys.executable, "__runner__.py"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            
            if res.returncode == 0:
                try:
                    parsed = json.loads(res.stdout)
                    return {"parsed": parsed, "stdout": res.stdout, "stderr": res.stderr, "exit_code": 0}
                except:
                     return {"parsed": None, "stdout": res.stdout, "stderr": res.stderr, "exit_code": 0}
            else:
                return {"parsed": None, "stdout": res.stdout, "stderr": res.stderr, "exit_code": res.returncode}
                
        except subprocess.TimeoutExpired:
            return {"timed_out": True, "stdout": "", "stderr": "Timeout"}
        except Exception as e:
            return {"stdout": "", "stderr": str(e)}

def run_cli_oracle(code_text, tests, timeout_sec_per_test, stdout_max_bytes, stderr_max_bytes, sandbox_mode, resource_limits, workspace_files=None, entrypoint=None):
    # CLI Runner
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup Workspace
        if workspace_files:
            setup_workspace(temp_dir, workspace_files)
            target_script = entrypoint if entrypoint else "main.py"
        else:
            target_script = "main.py"
            with open(os.path.join(temp_dir, target_script), "w", encoding="utf-8") as f:
                f.write(code_text or "")
                
        parsed = {"passed": 0, "failed": 0, "failures": []}
        
        for t in tests:
            inp = t["input"]
            expected = t["expected"]
            
            # Determine stdin and args
            # Contract: input can be string (stdin) or dict {stdin, argv, files}
            stdin_data = ""
            argv = []
            
            if isinstance(inp, dict):
                stdin_data = inp.get("stdin", "")
                argv = inp.get("argv", [])
                # Optional: Support per-test file setup? 
                # For now, let's assume workspace covers static files.
                # If tests need dynamic files, we might need to write them here.
                test_files = inp.get("files", {})
                if test_files:
                    setup_workspace(temp_dir, test_files) # Overwrite/Add
            else:
                stdin_data = str(inp)
            
            # Construct Command
            # python target_script [args]
            cmd = [sys.executable, target_script] + argv
            
            try:
                res = subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec_per_test
                )
                
                # Matching
                got = res.stdout.strip()
                
                # Check expected type
                # If expected is dict with 'files', perform file validation
                expected_stdout = ""
                expected_files = {}
                
                if isinstance(expected, dict):
                    expected_stdout = str(expected.get("stdout", "")).strip()
                    expected_files = expected.get("files", {})
                else:
                    expected_stdout = str(expected).strip()
                
                # 1. Compare Stdout
                match_stdout = got == expected_stdout
                
                # 2. Compare Output Files
                match_files = True
                failed_files = []
                
                for fpath, fcontent in expected_files.items():
                    full_fpath = os.path.join(temp_dir, fpath)
                    if not os.path.exists(full_fpath):
                        match_files = False
                        failed_files.append(f"{fpath} (missing)")
                        continue
                        
                    try:
                        with open(full_fpath, "r", encoding="utf-8") as f:
                            actual_content = f.read().strip()
                        if actual_content != fcontent.strip():
                            match_files = False
                            failed_files.append(f"{fpath} (content mismatch)")
                    except Exception as e:
                        match_files = False
                        failed_files.append(f"{fpath} (read error: {e})")
                
                if match_stdout and match_files:
                    parsed["passed"] += 1
                else:
                    parsed["failed"] += 1
                    error_msg = res.stderr
                    if not match_files:
                        error_msg += f"\nFile validation failed: {', '.join(failed_files)}"
                    
                    parsed["failures"].append({
                        "test_name": t["name"],
                        "input": inp,
                        "expected": expected,
                        "got": got if match_files else f"stdout={got}, file_errors={failed_files}",
                        "error": error_msg
                    })
            except subprocess.TimeoutExpired:
                 parsed["failed"] += 1
                 parsed["failures"].append({"test_name": t["name"], "error": "Timeout"})
                 
        return {"parsed": parsed, "stdout": "", "stderr": "", "exit_code": 0}
