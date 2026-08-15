---
name: commit
description: Stage and commit the current working tree changes as one or more atomic, Conventional-Commit-formatted commits, following this repo's Commit Policy in CLAUDE.md. Use when the user asks to commit changes, wrap up work, or says "commit this".
---

# Commit

Turn the current working tree changes into atomic, Conventional Commit-formatted
commits, following the **Commit Policy (STRICT ATOMIC COMMITS)** already defined
in this repo's `CLAUDE.md`. Re-read that section if it has changed — this skill
implements it, it doesn't override it.

## Steps

1. **Inspect the working tree.**
   Run `git status --short` and `git diff` (and `git diff --staged` if anything
   is already staged) to see the full set of pending changes.

2. **Group into atomic units.**
   Identify how many *logically distinct* changes are present. A unit is one
   single responsibility — one feature, one fix, one refactor, one doc update,
   one config change. Never group unrelated changes (e.g. a bug fix and a new
   feature) into the same commit, even if they touch the same file — in that
   case, use `git add -p` to stage only the relevant hunks for each commit.

   If everything in the working tree is genuinely one unit, that's fine — one
   commit is still atomic. If it's clearly several, say so and propose the
   split explicitly before doing anything.

3. **For each atomic unit, in order:**
   - State exactly which files (or hunks) will be staged for this commit.
   - Draft a Conventional Commit message: `<type>: <description>`, where
     `<type>` is one of `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
     The description explains *what* changed and, where it's not obvious,
     *why*.
   - Show the staged files and the exact proposed message to the user.
   - **Wait for explicit approval before running `git commit`.** Do not commit
     on an assumption of approval — this matches the repo's "Explicit
     Approval" rule. A general "go ahead" covering the whole session's work is
     sufficient; when in doubt, ask.
   - After approval, stage exactly those files/hunks and commit with that
     exact message.

4. **Repeat** until the working tree is clean or the user says to stop.

5. **Never combine steps 3 and 4 across units** — each commit must leave the
   repository in a working, self-contained state per the "Always Functional &
   Compilable" rule. If a unit can't stand alone (e.g. it depends on a file
   from a not-yet-committed unit), commit its dependency first.

## Notes

- If the user has already told you in this conversation to proceed without
  per-step pauses, you may skip the per-unit confirmation in step 3 but you
  must still keep commits atomic (one logical unit per commit) and still
  report the final list of commits made.
- Don't invent scope. If it's unclear whether two changes belong in the same
  commit, ask rather than guessing.
- Match the message style already in this repo's history (`git log --oneline`)
  — short, imperative, `type: description`, no trailing period.
