"""Helper modules for the chat orchestrator (see backend/solution.py).

Module map, in the order a request flows through them:

    config.py        models, budgets, timeouts, the fixture's frozen clock
    clusters.py      the routing taxonomy: 191 tools -> 36 clusters, plus the
                     per-tool behavioural hints that encode fixture gotchas
    catalog.py       static index built once at import; read/write classification
    router.py        Stage 0 lexical scorer -> confidence gate -> Stage 1 LLM
    toolfinder.py    `find_tools`, the mid-turn escape hatch from a routing miss
    schema.py        compressed Chat Completions schemas with a truthful
                     `required` list (main.py's forces all 929 properties)
    prompts.py       system prompt, including the environment facts that
                     prevent whole classes of error
    loop.py          the bounded orchestration loop; four termination paths
    executor.py      the single choke point: sanitise -> invoke -> unwrap ->
                     catch -> log. Every tool call goes through here, which is
                     why none can be made without appearing in tool_calls.
    policy.py        destructive-tool guards, duplicate/retry rules
    compaction.py    shrink results for the model's context only; the full
                     result is always what gets logged
    observability.py one structured trace line per turn

`helpers.py` re-exports the public surface so solution.py stays one import wide.
"""
