# Refactor Pass — PR Code Quality

You are performing a refactoring pass on recently changed files in this project.

Working directory: `{PROJECT_PATH}`

## Your Task

1. Run `git diff HEAD~3..HEAD --name-only` to identify files changed in recent commits.
2. Read each changed file and look for:
   - Duplicated code that can be factored out
   - Overly complex functions that can be simplified
   - Dead code or unused imports
   - Naming inconsistencies
   - Missing or incorrect type hints (if the project uses them)
3. Apply **minimal, focused refactoring** — each change should be clearly an improvement.
4. Do NOT change behavior, only structure and clarity.
5. Do NOT add new features, comments, or docstrings unless fixing something broken.
6. Prefer small, obvious improvements over ambitious restructuring.

Output a brief summary of what you refactored.
