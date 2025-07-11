# Gemini Agent Operating Principles

This document outlines the core principles and best practices for the Gemini agent's operation within this project. These guidelines are established to ensure efficient, safe, and consistent development.

## Core Principles:

1.  **Strict Adherence to `task-master` CLI**: The agent shall exclusively use the `task-master` command-line interface for all task management operations, including updating task statuses, adding new tasks, or modifying existing task details. Direct manipulation of task files (e.g., within `.taskmaster/tasks/`) is strictly prohibited.

2.  **Critical Task Status Management**: The agent MUST maintain accurate project tracking through proper task status management. This applies to EVERY task without exception:
    
    **When Starting a Task** - IMMEDIATELY mark as in-progress:
    ```bash
    task-master set-status --id=<id> --status=in-progress
    ```
    - Execute this BEFORE beginning any implementation work
    - Maintain only ONE task in-progress at a time
    
    **During Implementation** - Log progress continuously:
    ```bash
    task-master update-subtask --id=<id> --prompt="implementation notes..."
    ```
    - Document current work progress and decisions made
    - Log challenges encountered and solutions implemented
    - Record architectural decisions and implementation details
    
    **When Completing a Task** - Mark as done only when fully complete:
    ```bash
    task-master set-status --id=<id> --status=done
    ```
    - Ensure ALL verification steps are completed successfully
    - Verify implementation meets all requirements
    - Confirm all tests pass and code quality standards are met

3.  **Prioritize Virtual Environments**: All Python-related installations and executions shall be performed within a virtual environment (e.g., `.venv`). The agent must ensure the virtual environment is activated before executing `pip install` commands or running Python scripts.

4.  **Thorough Verification Before Marking as `done`**: Before marking any task or subtask as `done`, the agent must ensure comprehensive verification. This includes:
    *   All code changes are fully implemented.
    *   Relevant tests (unit, integration, etc.) are written and pass successfully.
    *   Code quality tools (linters, formatters like `black`, `flake8`, `mypy`) have been run and passed.
    *   New functionalities have been validated to meet expectations, even if through basic checks (e.g., module import, class instantiation).
    *   All dependencies are correctly handled and installed.

5.  **Incremental Progress and Status Updates**: Tasks will be marked `in-progress` upon commencement and only transitioned to `done` after all verification steps are successfully completed.

6.  **Adherence to Project Conventions**: The agent will consistently analyze existing code, file structures, and configurations to ensure that all new additions or modifications align with established project conventions (e.g., naming, formatting, architectural patterns).

7.  **Clear Communication**: If a task requires external setup or dependencies (e.g., Celery requiring a Redis server), the agent will clearly communicate these requirements to the user.

## Future Enhancements:

-   **Automated Testing Integration**: Explore integrating automated test execution as a mandatory step before marking tasks as complete.
-   **Linter/Formatter Enforcement**: Ensure pre-commit hooks or CI/CD pipelines enforce code quality standards.
