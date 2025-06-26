# Contributing to Jarvis AGI

First off, thank you for considering contributing to Jarvis AGI! It's people like you that make Jarvis AGI such a great tool.

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible using our bug report template.

**Great Bug Reports** tend to have:
- A quick summary and/or background
- Steps to reproduce
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please use our feature request template and include:
- Use case for the feature
- Current workaround (if any)
- Proposed solution
- Alternative solutions considered

### Pull Requests

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code follows the style guidelines
6. Issue that pull request!

## Development Process

### Setup Development Environment

```bash
# Clone your fork
git clone https://github.com/yourusername/jarvis.git
cd jarvis

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Code Style

We use several tools to maintain code quality:

- **Black** for code formatting
- **Flake8** for linting
- **MyPy** for type checking

Run these before committing:

```bash
make format    # Format code with Black
make lint      # Check with Flake8
make type-check # Check types with MyPy
```

### Testing

Always write tests for new functionality:

```bash
# Run all tests
make test

# Run with coverage
make coverage

# Run specific test file
pytest tests/unit/test_example.py
```

### Commit Messages

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only changes
- `style:` Code style changes (formatting, etc)
- `refactor:` Code change that neither fixes a bug nor adds a feature
- `perf:` Performance improvement
- `test:` Adding missing tests
- `chore:` Changes to build process or auxiliary tools

Example: `feat: add new memory storage backend`

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring

### Pull Request Process

1. Update the README.md with details of changes if needed
2. Update the CHANGELOG.md following the Keep a Changelog format
3. Ensure all tests pass and coverage doesn't decrease
4. Request review from maintainers
5. Once approved, the PR will be merged

### Project Management

We use Task Master AI for project management. If you're working on a specific task:

```bash
# View available tasks
task-master list

# Get details of a task
task-master show <task-id>

# Update task status
task-master set-status --id=<task-id> --status=in-progress
```

## Style Guidelines

### Python Style Guide

- Follow PEP 8
- Use type hints for all function signatures
- Write docstrings for all public modules, functions, classes, and methods
- Keep functions focused and small
- Prefer composition over inheritance

### Documentation Style

- Use clear, concise language
- Include code examples where helpful
- Keep documentation up-to-date with code changes
- Use proper markdown formatting

### Testing Guidelines

- Write tests for all new functionality
- Aim for at least 80% code coverage
- Use descriptive test names
- Follow the Arrange-Act-Assert pattern
- Mock external dependencies

## Recognition

Contributors will be recognized in the README.md file. We value all contributions, big and small!

## Questions?

Feel free to open an issue with the "question" label or reach out to the maintainers directly.

Thank you for contributing to Jarvis AGI! 🚀