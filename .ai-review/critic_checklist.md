# AI Critic Checklist

- [ ] Does this PR adhere to the current version's (e.g. v1) scope? 
- [ ] Are we falling back to full schema? (This is strictly prohibited).
- [ ] Is every decision recorded in the trace store?
- [ ] Are hub penalties respected when traversing the graph?
- [ ] Did we ensure that LLM is an assistant/recommender and not a direct decision maker without constraints?
- [ ] Are test queries passing the benchmark?
- [ ] Did we avoid introducing GraphRAG/PPR concepts prematurely before v1 is stable?
