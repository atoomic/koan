# Quality Review Pass — PR Improvements

You are performing a quality review on recently changed files in this project.

Working directory: `{PROJECT_PATH}`

## Your Task

1. Run `git diff HEAD~3..HEAD --name-only` to identify files changed in recent commits.
2. Read each changed file and check for:
   - Security issues (injection, XSS, unsafe deserialization, hardcoded secrets)
   - Error handling gaps (missing try/catch, unhandled edge cases)
   - Logic bugs or race conditions
   - Test coverage gaps for new code
   - API consistency issues
3. **Fix issues you find** — don't just report them.
4. For each fix, ensure it's minimal and doesn't change unrelated code.
5. If you find issues but the fix would be too invasive, note them as comments in the code.

Output a brief summary of what you found and fixed.
