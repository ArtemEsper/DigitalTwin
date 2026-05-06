---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when the user wants to stress test a plan, get grilled on their design, or mentions "grill-me".
---

# Grill Me

Interview the user relentlessly about every aspect of the plan or design until there is a shared understanding.

Walk down each branch of the design tree and resolve dependencies between decisions one by one.

For each question, provide your recommended answer before asking the user to respond.

Ask only one question at a time.

If a question can be answered by exploring the codebase, explore the codebase instead of asking the user.

## Behavior

When this skill is triggered:

1. Identify the plan, design, architecture, implementation, or decision that needs to be stress-tested.
2. Build an implicit decision tree covering:
   - goals and success criteria
   - users and stakeholders
   - constraints
   - assumptions
   - architecture
   - data flow
   - dependencies
   - risks
   - failure modes
   - trade-offs
   - testing and validation
   - deployment and operations
   - maintainability
3. Start with the highest-impact unresolved decision.
4. Ask one question only.
5. For every question, include:
   - why the question matters
   - the recommended answer
   - the question itself
6. After the user answers, update the shared understanding and continue to the next unresolved branch.
7. Do not move to unrelated branches until the current dependency chain is resolved.
8. If the answer is discoverable from the repository, inspect the relevant files instead of asking.

## Question Format

Use this format:

```text
Why this matters:
<brief explanation>

Recommended answer:
<your recommended answer based on the current context>

Question:
<one clear question for the user>
```
