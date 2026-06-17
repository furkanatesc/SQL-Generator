# v1 — Controlled Production Baseline

## Amaç
İlk hedefimiz “çok akıllı sistem” değil; patlamayan, debug edilebilen, ölçülebilen ve production’a alınabilecek güvenli sistem.
v1’de sistemin her kararını görebilmeliyiz.

## Kapsam
1. Tokenizer düzeltmesi
2. Auto Schema Lexicon
3. SQLite Synonym Registry
4. Candidate Scoring
5. RAG Threshold
6. Hub Penalty
7. Bounded Graph Traversal
8. Token Budget
9. Trace Store
10. SQL Validation

## Çıktılar
- SchemaLexiconBuilder
- SynonymRepository
- CandidateScorer
- GraphBackend interface
- NetworkXGraphBackend
- BoundedGraphPruner
- TraceStore
- SQLValidator
- Golden Query Test Set
- /debug/traces endpointleri

## Başarı Kriterleri
- Golden query sayısı: 50–100
- Table Recall: >= 0.90
- Invalid SQL Rate: <= %10
- Schema token reduction: >= %70
- Full schema fallback: neredeyse sıfır
- Trace coverage: %100
