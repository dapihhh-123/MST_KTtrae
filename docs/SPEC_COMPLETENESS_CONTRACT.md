# Spec Completeness Contract

This document defines the requirements for a "Complete" Spec produced by the Analyze Task module.

## 1. Universal Requirements (All Task Types)
Every generated Spec MUST contain:
- **goal_one_liner**: A concise, single-sentence summary of the task.
- **deliverable**: One of `function`, `cli`, `script`.
- **language**: Target language (e.g., `python`).
- **runtime**: Execution environment (e.g., `python`).
- **constraints**: A list of explicit hard constraints (e.g., "Do not use external libraries").
- **assumptions**: A list of defaults applied (e.g., "Assume valid input").

## 2. Type-Specific Requirements

### A. Function (Single/Stateless)
- **signature**: Must have `function_name`, `args` (list of strings), and `returns` (type string).
- **output_shape**: JSON schema describing the return value structure.
- **public_examples**: At least 3 examples with `input` and `expected`.

### B. CLI (Stdin/Stdout)
- **signature**: `function_name` usually `main` or entrypoint.
- **output_shape**: JSON schema describing the stdout structure (if applicable) or just "string".
- **input_format**: Explicit description of stdin format in `constraints` or `assumptions`.
- **public_examples**: `input` is stdin content, `expected` is stdout content.

### C. Stateful Ops (Sequence)
- **signature**: `function_name` (e.g., `solve`), `args` (e.g., `['ops']`), `returns` (e.g., `list`).
- **output_ops**: List of operation names that produce output (e.g., `['query', 'get']`).
- **output_shape**: Schema of the *items* in the returned list.
- **ambiguities**: Must clarify invalid op behavior if not specified.

## 3. Ambiguity vs. Assumption Policy
- **Ambiguity**: Critical missing information that drastically changes implementation (e.g., "Overwrite vs. Ignore duplicate ID?"). MUST be asked if confidence < 0.9.
- **Assumption**: Safe defaults for minor details (e.g., "Input ID is integer"). MUST be recorded in `assumptions`.

## 4. Validation Rules
- **Schema Compliance**: All JSON fields must match `TaskSpec` Pydantic model.
- **No Hallucinations**: Do not invent constraints not implied by the user task.
- **Self-Correction**: If LLM output fails schema validation, retry with error feedback (handled by pipeline).
