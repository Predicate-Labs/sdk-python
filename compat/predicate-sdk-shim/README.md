# predicate-sdk compatibility shim

This package exists to preserve install compatibility for users who still run:

```bash
pip install predicate-sdk
```

It depends on `predicate-runtime` and does not provide a separate runtime surface.
Use canonical imports from `predicate` in your code.
