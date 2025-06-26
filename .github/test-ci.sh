#!/bin/bash
# Test script to verify CI/CD setup

echo "Testing CI/CD Pipeline Configuration"
echo "===================================="

# Check if all workflow files are valid YAML
echo -n "Checking workflow files... "
for file in .github/workflows/*.yml; do
    .venv/bin/python -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null || {
        echo "FAILED: $file is not valid YAML"
        exit 1
    }
done
echo "OK"

# Check if Docker files exist
echo -n "Checking Docker files... "
[ -f Dockerfile ] && [ -f docker-compose.yml ] && [ -f .dockerignore ] && echo "OK" || {
    echo "FAILED: Missing Docker files"
    exit 1
}

# Check if Python packaging files exist
echo -n "Checking packaging files... "
[ -f setup.py ] && [ -f pyproject.toml ] && echo "OK" || {
    echo "FAILED: Missing packaging files"
    exit 1
}

# Check if all required directories exist
echo -n "Checking directory structure... "
[ -d .github/workflows ] && [ -d .github/ISSUE_TEMPLATE ] && echo "OK" || {
    echo "FAILED: Missing required directories"
    exit 1
}

echo ""
echo "All CI/CD checks passed!"