# Judge case corpus

`conversation_cases.json` is a versioned semantic corpus for Judge Prompt evaluation. It includes
natural confirmations, complete answers, pending upstream tasks, questions, corrections, emotion,
Prompt Injection, and ambiguous exchanges.

The default CI suite deliberately does **not** call a paid or external LLM. It verifies:

- corpus shape and category coverage;
- preservation of the latest user message in the bounded Judge payload;
- strict three-state orchestration when a mocked Judge returns each expected label;
- the rule that only high-confidence `END` may stop an event.

It does not claim that a real model will produce the expected label. Before changing
`SYSTEM_PROMPT` or releasing with a new recommended Provider, evaluate every case against that
Provider with temperature set as low as the Provider actually supports, record the model/version,
and manually review all mismatches. Any false `END` is release-blocking; `UNCERTAIN` is treated as
`CONTINUE`.

Never replace this evaluation with keyword heuristics inside the plugin or commit real private
conversations to the corpus.
