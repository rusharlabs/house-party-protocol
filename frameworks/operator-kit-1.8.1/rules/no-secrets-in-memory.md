# No Secrets in Memory Files

> **Auto-Trigger:** memory, credentials, API key, token, webhook
> **Keywords:** "memory", "credentials", "API key", "secret", "token"
> **Priority:** CRITICAL

## Rule

NEVER store API keys, tokens, webhook URLs, passwords, or any credentials as plaintext values in:
- MEMORY.md or auto-memory files
- CLAUDE.md files
- Rule files
- Any file that is committed to git or persists across sessions

Use reference-only entries pointing to `.env`:
- CORRECT: "Example service API key: stored in `.env` as `EXAMPLE_SERVICE_API_KEY`"
- WRONG: "Example service API key: a1b2c3d4-0000-..."

## Enforcement

If you detect a secret being written to a memory or config file:
1. STOP the write
2. WARN the user
3. Suggest storing in `.env` instead
