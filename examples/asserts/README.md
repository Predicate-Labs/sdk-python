# Assertions examples (v1 + v2)

These examples focus on **AgentRuntime assertions**:

- **v1**: deterministic, state-aware assertions (enabled/checked/value/expanded) + failure intelligence
- **v2**: `.eventually()` retry loops with `min_confidence` gating + snapshot exhaustion, plus optional Python vision fallback

Run examples:

```bash
cd sdk-python
python examples/asserts/state_assertions.py
python examples/asserts/eventually_min_confidence.py
python examples/asserts/vision_fallback.py
```
