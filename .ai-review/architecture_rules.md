# Architecture Rules

1. **Deterministic Baseline First:** Implement deterministic rules before attempting advanced graph optimizations or LLM-driven autonomous decisions.
2. **LLM is not the Decider:** The LLM should generate SQL and suggest rules, but NOT make the final table/column selection autonomously without constraints.
3. **Trace Everything:** If a table is selected or dropped, the reason must be logged.
4. **No Full Schema Fallback:** Do not pass the entire schema to the LLM when unsure. Fail gracefully or ask for clarification.
5. **Enforce Budgets:** Respect token budgets when constructing prompts. Prune effectively.
