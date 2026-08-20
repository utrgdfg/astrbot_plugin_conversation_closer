# Release checklist

## Repository and identity

- [x] `metadata.yaml` identity is `utrgdfg/astrbot_plugin_conversation_closer`.
- [x] Version is `0.2.0` in package, metadata, project metadata, and changelog.
- [x] Repository URL uses HTTPS GitHub.
- [x] MIT license, security policy, contribution guide, changelog, and a 256×256 root `logo.png` are present.
- [ ] Confirm redistribution rights for the user-supplied `logo.png` before marketplace submission.
- [ ] Confirm the GitHub repository is public before marketplace submission.
- [ ] Add a concise GitHub description and relevant repository topics.

## Compatibility and live validation

- [x] Automated tests cover Python 3.12-compatible code and CI targets 3.12–3.14.
- [x] Minimum AstrBot version is `>=4.24.2,<5`, based on LLM API availability and
      persistent `stop_event()` propagation behavior.
- [x] `support_platforms` is intentionally omitted until real adapter tests are complete.
- [ ] Install the plugin into a clean current AstrBot instance from the GitHub URL.
- [ ] Select a real low-cost Judge Provider and test strict JSON output.
- [ ] Run private-chat smoke tests on each platform that will be declared.
- [ ] Run group-chat tests before enabling or declaring experimental group support.

## Behavior and safety

- [x] Only `END` plus the configured confidence threshold can call `stop_event()`.
- [x] `CONTINUE`, `UNCERTAIN`, missing providers, timeouts, invalid JSON, and exceptions fail open.
- [x] No keyword-only stop path, random reply probability, proactive reply, or reply-desire logic exists.
- [x] Session history, dedupe state, and locks are bounded and cleaned by TTL/termination.
- [x] Commands bypass the Judge and do not pollute conversation history.
- [x] Privacy, Provider cost, Prompt Injection, logging, and known limitations are documented.
- [ ] Review Judge results against real conversational traffic without logging private full histories.

## Quality gates

- [x] Python compilation succeeds.
- [x] Ruff succeeds.
- [x] Pytest succeeds without real LLM or credentials.
- [x] Bandit succeeds.
- [x] Secret, local-path, dangerous execution, and hidden-network scans return zero findings.
- [ ] Confirm GitHub Actions succeeds after push.

## Publish

- [ ] Merge the reviewed branch into the repository default branch.
- [ ] Create signed or annotated tag `v0.2.0` after the merge commit is final.
- [ ] Create a GitHub release using the matching changelog entry.
- [ ] Register/sign in to AstrBot Cloud and open the official plugin publish page.
- [ ] Submit the public repository URL and verify `author`, `name`, and `version` remain unchanged.
- [ ] Confirm the marketplace package is below the official 16 MB limit.
- [ ] Reinstall the marketplace build and repeat a private-chat smoke test.
