# v3 — GraphRAG / PPR / Dynamic Subgraph Optimizer

## Amaç
Daha ileri graph tabanlı optimizasyona geçiyoruz. Büyük şemalarda yüksek recall, düşük token maliyeti, daha doğru join path, daha az hub patlaması.

## Kapsam
1. Directed Weighted Schema Graph
2. Personalized PageRank
3. Weighted Shortest Path
4. Dynamic Subgraph Optimization
5. Column-Level Pruning
6. Multi-Candidate SQL Generation
7. Execution-Guided Repair

## Çıktılar
- DirectedWeightedSchemaGraph
- PersonalizedPageRankService
- WeightedShortestPathService
- DynamicSubgraphOptimizer
- ColumnPruner
- JoinPathConfidenceScorer
- MultiCandidateSQLGenerator
- ExecutionGuidedRepair

## Başarı Kriterleri
- Golden query sayısı: 300–700
- Table Recall: >= 0.96
- Column Recall: >= 0.93
- Invalid SQL Rate: <= %5
- Token reduction: >= %85
- Join error rate belirgin düşmeli
- P95 latency kabul edilebilir seviyede olmalı
