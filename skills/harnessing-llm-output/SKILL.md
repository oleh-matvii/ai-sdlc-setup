---
name: harnessing-llm-output
description: Use when writing or changing application code that calls an LLM and consumes its output, or that adds or edits a prompt the app sends - wraps every call site in a harness (schema, validation retry, attempt history, prompt version)
---

# Harnessing LLM output

Model output is **untrusted input**. A call site is done only when malformed output is parsed, retried, or failed as a typed error, never passed on as text that merely looks right. The prompt is a version of business logic and changes the way code does.

## Steps for every call site

1. **Schema at the boundary.** Declare the expected shape once (Zod in TS, Pydantic in Python) and parse the response with it. Use the provider's native structured output (JSON schema / tool input) when it has one, and parse anyway: native modes reduce failures, they do not remove them. Look up the current SDK API through context7 before writing it.
2. **Bounded validation retry.** On a parse failure, call again with the validation error text appended, up to a named `MAX_VALIDATION_ATTEMPTS` (2–3). After the last attempt return a typed failure (`Result` / domain error) that the caller must handle.
3. **Attempt history.** Record each attempt through an injected recorder: prompt version, attempt number, raw output, validation outcome, tokens and latency. This history is what later evals and debugging read.
4. **Versioned prompt.** The prompt lives in its own file or named constant with an explicit version id, and that id goes into every attempt record. Changing the wording bumps the version.
5. **Model behind a seam.** The model client is injected I/O. Business logic receives the parsed, typed value and never sees raw text. The parse-and-retry loop is its own unit.

## Tests

At the model seam, use a fake client that returns scripted outputs. Each of these must be seen red first:
- valid output → typed value reaches the business logic
- invalid then valid → one retry, and the second request carries the validation error
- invalid on every attempt → typed failure after `MAX_VALIDATION_ATTEMPTS`, with no further call
- the prompt version appears in the attempt record

## Done when

Every LLM call site touched by the change has all five steps and the four tests, and the completion report lists the call sites with their prompt versions.
