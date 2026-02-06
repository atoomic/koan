# PR Review — Address Feedback

You are reviewing a pull request and implementing the changes requested by reviewers.

## Pull Request: {TITLE}

**Branch**: `{BRANCH}` → `{BASE}`

### PR Description

{BODY}

---

## Current Diff

```diff
{DIFF}
```

---

## Review Comments (inline on code)

{REVIEW_COMMENTS}

## Reviews (top-level)

{REVIEWS}

## Conversation Thread

{ISSUE_COMMENTS}

---

## Your Task

1. **Read the review comments carefully.** Understand what changes are being requested.
2. **Implement the requested changes.** Edit the code to address each review comment.
   - If a comment is a question or discussion (not a change request), skip it.
   - If a comment requests a change that would break functionality, note it but still implement it.
3. **Run the test suite** to make sure your changes don't break anything.
   - Look for a Makefile, package.json, or similar to find the test command.
   - If tests fail, fix them.
4. **Be thorough but focused.** Only change what reviewers asked for — no drive-by refactoring.

When you're done, output a concise summary of what you changed and why.
