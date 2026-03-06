# BOOTSTRAP.md - Startup Checklist

Use this checklist on first run or after major config reset.

## 1. Load Runtime Context

Read in order:

1. `IDENTITY.md`
2. `SOUL.md`
3. `AGENTS.md`
4. `TOOLS.md`
5. `USER.md`
6. `MEMORY.md` (if present)

## 2. Self-Check

1. Confirm discovery endpoint is reachable.
2. Confirm at least one critical tool exists: `hello.greet`.
3. Confirm invoke path is configured to Core A2A endpoint.

If any check fails, run fail-closed behavior:

- Report temporary routing issue.
- Do not fabricate domain answers.

## 3. First User Turn

1. Send concise greeting.
2. Ask for task intent only if not provided.
3. Route immediately when intent is clear.

## 4. Memory Hygiene

1. Store durable preferences and project facts in `MEMORY.md`.
2. Never store credentials/secrets in markdown memory files.
