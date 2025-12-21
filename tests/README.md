# Running Tests - Python SDK

## Prerequisites

```bash
cd sdk-python
pip install -e ".[dev]"
playwright install chromium
```

## Running All Tests

```bash
# From sdk-python directory
pytest tests/

# With verbose output
pytest tests/ -v

# With even more detail
pytest tests/ -vv
```

## Running Specific Test Files

```bash
# Run only inspector tests
pytest tests/test_inspector.py

# Run only recorder tests
pytest tests/test_recorder.py

# Run only generator tests
pytest tests/test_generator.py

# Run only smart selector tests
pytest tests/test_smart_selector.py

# Run only snapshot tests
pytest tests/test_snapshot.py

# Run only query tests
pytest tests/test_query.py

# Run only action tests
pytest tests/test_actions.py

# Run only wait tests
pytest tests/test_wait.py

# Run only spec validation tests
pytest tests/test_spec_validation.py
```

## Running Specific Test Functions

```bash
# Run a specific test function
pytest tests/test_inspector.py::test_inspector_start_stop

# Run multiple specific tests
pytest tests/test_recorder.py::test_recorder_click tests/test_recorder.py::test_recorder_type
```

## Running Tests with Output

```bash
# Show print statements
pytest tests/ -s

# Show print statements + verbose
pytest tests/ -sv

# Show local variables on failure
pytest tests/ -l
```

## Running Tests in Parallel

```bash
# Install pytest-xdist first: pip install pytest-xdist
pytest tests/ -n auto
```

## Running Tests with Coverage

```bash
# Install pytest-cov first: pip install pytest-cov
pytest tests/ --cov=sentience --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Common Options

```bash
# Stop on first failure
pytest tests/ -x

# Stop after N failures
pytest tests/ --maxfail=3

# Run only tests matching a pattern
pytest tests/ -k "inspector"

# Run tests and show slowest 10
pytest tests/ --durations=10

# Run tests with markers (if defined)
pytest tests/ -m "not slow"
```

## Example: Full Test Run

```bash
cd sdk-python
pytest tests/ -v --tb=short
```

## Example: Quick Smoke Test

```bash
cd sdk-python
pytest tests/test_snapshot.py::test_snapshot_basic -v
```

## Troubleshooting

### Browser not found
```bash
playwright install chromium
```

### Extension not found
Make sure the extension is built:
```bash
cd ../sentience-chrome
./build.sh
```

### Import errors
Make sure the package is installed in development mode:
```bash
pip install -e ".[dev]"
```

