# Contributing

Contributions are welcome when they preserve the plugin's narrow semantic contract: classify
whether the current exchange is already complete. Do not add random reply probabilities, reply
desire, mood, proactive messaging, or keyword-only suppression.

## Development

1. Use Python 3.12 or newer.
2. Install the development extras: `python -m pip install -e ".[dev]"`.
3. Run `ruff check .` and `pytest` before opening a pull request.
4. Add or update cases in `tests/cases/conversation_cases.json` for prompt changes.

LLM calls in tests must always be mocked. Never commit credentials or private chat logs.
