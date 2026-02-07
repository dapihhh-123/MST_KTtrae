# TODO: JSON Validator

## Immediate Next Steps
- [ ] **Integration with Frontend**: Ensure the frontend correctly displays the `fail_reasons` when a task fails analysis, so users (or developers) can see why the spec was rejected.
- [ ] **Refine Interaction Models**: Currently `cli_stdio` tasks are sometimes failing validation due to strict type checking on examples (R2/R3). We need to support `str` return types for CLI tasks more explicitly or adjust the validator to be lenient for CLI.

## Future Improvements
- [ ] **More Granular Ambiguity Types**: Add detection for "Input Format" ambiguities, not just "Output Format".
- [ ] **Self-Correction**: Allow the LLM to auto-correct the spec based on validator feedback without starting a fresh attempt (currently it retries the whole generation).
- [ ] **Unit Test Generation**: Use the validated spec to automatically generate Python `unittest` cases.
