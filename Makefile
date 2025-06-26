.PHONY: help install test test-unit test-integration test-performance test-all coverage lint format type-check clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	python -m pip install --upgrade pip
	pip install -r requirements.txt

test: ## Run all tests
	pytest -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	pytest tests/integration/ -v -m integration

test-performance: ## Run performance tests only
	pytest tests/performance/ -v -m performance

test-all: ## Run all tests with coverage
	pytest -v --cov=core --cov=modules --cov-report=term-missing --cov-report=html:htmlcov

coverage: ## Generate coverage report
	pytest --cov=core --cov=modules --cov-report=term-missing --cov-report=html:htmlcov
	@echo "Coverage report generated in htmlcov/index.html"

lint: ## Run flake8 linter
	flake8 core/ modules/ tests/

format: ## Format code with black
	black core/ modules/ tests/

type-check: ## Run mypy type checker
	mypy core/ modules/

clean: ## Clean up temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf .mypy_cache