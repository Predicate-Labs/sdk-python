#!/bin/bash
# Quick test runner script for Python SDK

echo "=== Running Python SDK Tests ==="
echo ""

# Check if in correct directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Must run from sdk-python directory"
    exit 1
fi

# Install dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -e ".[dev]" > /dev/null 2>&1
fi

# Run tests
echo "🧪 Running tests..."
pytest tests/ -v "$@"
