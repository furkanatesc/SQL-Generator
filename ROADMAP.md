# SQLGen — Yol Haritası (ROADMAP)

Bu dosya yol haritasının **tek giriş noktasıdır**. Eksen: **Phase → Sprint → PR**.

- Tamamlanan işler: `CHANGELOG.md` (özet) ve `docs/SPRINT-PR-LOG.md` (sprint/PR detayı)
- İleriye dönük plan: `docs/PLANNED-SPRINTS.md` (Phase 7–15 · Sprint 25.8 → 34.7)
- Teknik borç: `docs/TECH-DEBT.md`

> Eski `v1–v6` sürüm/olgunluk şeması terk edildi; plan artık faz/sprint
> üzerinden ilerliyor. Eski sürüm-tasarım notları `docs/archive/` altına
> taşındı (geçmiş referans). `SPRINTHARITASI.txt` ve `senioryolharitası.txt`
> eski/kişisel notlardır ve bu dosya tarafından geçersiz kılınmıştır.

---

## Şu an neredeyiz? (You are here)

| Durum | Kapsam | Detay |
|---|---|---|
| ✅ **Tamamlandı** | Sprint 0 → **27.10** | `v1.0.0` yayınlandı (tag `9907cd3`, 2026-06-18). Phase 6 (adapter stub'ları, #125/#126) ve **Phase 7 (Security & Governance, 26.0–26.11) kapandı**. **Phase 8 (Observability & Debuggability, 27.0–27.10) kapandı** — 27.0 End-to-End Trace Contract + 27.1 Remaining Stage Span Builders + 27.1w Live Trace Wiring (PR #135) + 27.2 Error Taxonomy v2 (PR #136) + 27.2.1 Error Taxonomy Boundary + **27.3 User Feedback Capture** (PR #139) + **27.4 Query Replay System** (PR #141) + **27.5 Debug Bundle Export** (PR #143) + **27.6 Metrics Contract** (PR #144) + **27.7 Admin Observability Dashboard Backend** (PR #145) + **27.8 Cost & LLM Usage Telemetry** (PR #146) + **27.9 Feedback Review → Rule Suggestion** (PR #147) + **27.10 Per-Release Accuracy Regression Gate** (PR #148) tamam. 27.5: yan etkisiz debug bundle (`GET /api/debug/jobs/{id}/bundle`). 27.6: pencere-bazlı versiyonlu metrik raporu (`GET /api/debug/metrics`). 27.7: 27.6 metriklerini birleştiren kompozit `GET /api/debug/dashboard`. 27.8: GENERATION span'lerinden LLM kullanımı + konfigüre edilebilir fiyat tablosuyla maliyet (`GET /api/debug/llm-usage`). 27.9: kullanıcı feedback'ini (27.3/27.7) aday `{natural_query→SQL}` kural önerisine çeviren yan etkisiz `GET /api/debug/rule-suggestions`. 27.10: golden eval raporunu tüketen, seeded baseline history'e karşı per-case/aggregate karşılaştırma yapan yan etkisiz CLI/CI regresyon gate'i (`evals/regression_gate_cli.py`) — debug endpoint değil, CI'a bağlanan tek istisna. `docs/SPRINT-PR-LOG.md` |
| 🔧 **Bakım (sprint dışı)** | **27.11 Tech-Debt Cleanup** | Phase 8 kapandıktan sonra, faz ilerletmeyen bir bakım sprinti: davranış korunur, yalnız test-bütünlüğü/invariant/sağlamlık iyileşir. `docs/TECH-DEBT.md`'deki 7 kalem ÇÖZÜLDÜ (§5.1 purity guard subprocess, §5.2 `expected_routes` snapshot-türev, §3 SKIPPED span `duration_ms`, §9.3 null-model uzlaşma, §8.2 `feedback_truncated`, §8.4(b) timeseries guard, §1 embedding dimension/doküman notu). Contract snapshot değişmedi. Full suite 2410 passed/9 skipped. `docs/SPRINT-PR-LOG.md` (PR #149) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.0** | **Large Schema Benchmark Suite** — Phase 9'un ilk sprint'i, **Phase 9 başladı**. Yeni `backend/benchmarks/` paketi (dev/CI aracı; hiçbir `app/` dosyası değişmedi): seeded sentetik şema üreteci (100/500/1000/2000 tablo) + frozen metrik sözleşmesi + 4 REUSED prodüksiyon hedefi için determinist metrik çıkarıcıları (`from_legacy_schema`/`find_join_paths`/`detect_implicit_relationships`/`select_schema_context`) + 27.10 desenini izleyen `compare_benchmark` + enjekte-clock'lu runner (`wall_ms` yalnız bilgi amaçlı) + CLI (`--gate`/`--update-baseline`, exit 0/1/2) + seeded committed baseline. İç patlama sayaçları/CI perf-gate/NetworkX pruner/embedding benchmark'ları bilinçli olarak 28.1+'a ertelendi (`docs/TECH-DEBT.md` §12). `docs/SPRINT-PR-LOG.md` (PR #150) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.1** | **Schema Graph Performance Profiling** — opsiyonel sıfır-ek-yük `ProfileProbe` (`app/schema/profiling.py`) üç seam'e (`find_join_paths`/`detect_implicit_relationships`/`select_schema_context`) iplendi, davranış korunur (`probe=None` byte-for-byte aynı). Benchmark v2: determinist iç patlama sayaçları (`dfs_visit`/`fuzzy_comparison`/vb.) + yeni 5. `graph_backend` hedefi (NetworkX build/pagerank/shortest_path, pagerank gate'lenmez) + baseline `large_schema_benchmark_v2` (100/500/1000 gate'lenir) + CI perf-gate adımı. TECH-DEBT §12'nin 3 kalemi ÇÖZÜLDÜ; embedding/RAG benchmark'ı (→28.8) ve pruner derin-probe AÇIK kaldı. `docs/SPRINT-PR-LOG.md` (PR #151) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.2** | **Join Path Explosion Control** — `find_join_paths`'in kombinatoryal DFS patlamasını iki katmanla sınırlayan ve yeni `JoinPathSearchResult` döndüren sprint (13 çağrı noktası `.paths`'e taşındı). Katman 1: çıktı-koruyan branch-and-bound (BFS admissible bound + kept-set dominance pruning, byte-for-byte aynı çıktı, brute-force denklik testiyle guard'lı). Katman 2: determinist `node_budget` güvenlik kemeri (`DEFAULT_JOIN_PATH_NODE_BUDGET = 200_000`, `budget_truncated` bayrağı). `select_schema_context` yeni `join_search_truncated` alanı kazandı (non-breaking). Benchmark v3 (100/500/1000 gate'lenir) join_paths hedefinde `dfs_visit`/`adjacency_edge`'de büyük düşüş ölçtü, çıktı-türevli metrikler değişmedi. **Bilinçli kapsam dışı (TECH-DEBT §12):** path scoring/hub-penalty, `GraphPruner` derin entegrasyonu, adaptif budget tuning, frontend `maxNodesLimit`. `docs/SPRINT-PR-LOG.md` (PR #152) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.3** | **Table Selection Cost Model** — `select_schema_context`'in hardcoded additive relevance skoru + düz top-K'sini config-driven bir benefit-vs-cost budget modeliyle değiştiren sprint. Yeni saf `app/schema/table_selection_cost.py`: frozen `TableSelectionCostModel` (named relevance ağırlıkları = eski magic number'lar + cost ağırlıkları `w_base`/`w_col`/`w_fk` + `cost_budget`), `table_cost()`, `fk_counts()`, toleranslı `from_config()` (27.8 `llm_pricing` deseni). `select_schema_context` enjekte edilen `cost_model=DEFAULT_COST_MODEL` kazandı (saf yaprak korunur). Seçim: exact-match focus tabloları önce garanti, kalanlar `cost_budget` altında benefit-density (`benefit/cost`) greedy ile eklenir, `max_tables` ikincil sert tavan. Şeffaflık: `SelectedTable.cost` + `SchemaContextSelection.total_cost`/`cost_budget`/`budget_exhausted`. `sql_pipeline.py`'de config anahtarı `table_selection_cost_model` → enjekte. Muhafazakâr varsayılan `cost_budget=30.0` golden şema üzerinde kalibre edildi (ölçülen max 25.0); golden eval yeşil, fixture kürasyonu gerekmedi. Benchmark v4: `context_selection` cost modelini yansıtır, `join_paths` metrikleri v3'e göre değişmedi. **Bilinçli kapsam dışı:** ilişki-güven-ağırlıklı komşu benefit'i (→ 28.4), token-tabanlı gerçek maliyet, gerçek 0/1-knapsack optimalliği, frontend `maxNodesLimit`. `docs/SPRINT-PR-LOG.md` (PR #153) |
| 🔧 **Bakım (sprint dışı)** | **28.3.1 Tech-Debt Cleanup** | 27.11 desenini izleyen, faz ilerletmeyen bakım sprinti: `docs/TECH-DEBT.md`'deki 10 kalem (4 bundle) ÇÖZÜLDÜ — §5.3 canlı SECURITY span outcome'ı 27.2 error registry'sinden türetiliyor, §8.1 feedback pencere sınırı naive-UTC normalize edildi, §8.4(a/c) debug gate + docstring notu, §6.1 debug bundle trace sorgusu `trace_type` ile doğrudan filtreleniyor, §12.16 fallback rejimi `budget_exhausted` çelişkisi kapandı, §12.17 uçtan-uca cost-model wiring testi, §12.6 scipy-eksik pagerank artık DEBUG logluyor, §11.3 regression-gate `--version` doğrulanıyor, §12.7 verify-close (kod değişikliği yok, 28.1–28.3'te zaten senkronlanmıştı). Yapısal borçlar (`scan_cap`→DB-aggregation, retry-token, onay-state, semantik dedup, gerçek-accuracy) bilinçli AÇIK. Full suite 2483 passed/9 skipped; CI perf-gate exit 0. `docs/SPRINT-PR-LOG.md` (PR #154) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.4** | **Relationship Confidence Scoring** — `TableSelectionCostModel`'in 28.3'te taşıdığı düz `explicit_neighbor`/`implicit_neighbor` (20.0/10.0) ağırlıklarını tek bir `neighbor_base: float = 20.0` ile birleştiren ve komşu benefit'ini çarpımsal (`neighbor_base × effective_confidence`) yapan sprint. `select_schema_context`'teki EXPLICIT/CUSTOM/IMPLICIT komşu genişletmesi artık ilişki güvenine göre ölçekleniyor (explicit/custom `confidence=None` → 1.0, implicit 0.60–0.90); `IMPLICIT_FUZZY` komşular yeni `include_fuzzy_neighbors` ile opt-in (varsayılan kapalı). `probe`/`node_budget`/`cost_budget`/seçim/join-path/fallback davranışı değişmedi. Muhafazakâr `neighbor_base=20.0` mevcut fixture'larda davranış-koruyucu; golden eval yeşil, fixture kürasyonu gerekmedi. Benchmark: versiyon bump gerekmedi — `context_selection` metrikleri committed v4 baseline'ıyla byte-identical (sentetik şema yalnız explicit-FK içeriyor); gate yeşil. TECH-DEBT §12.13 ÇÖZÜLDÜ. Full suite 2490 passed/9 skipped. `docs/SPRINT-PR-LOG.md` (PR #155) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.5** | **Missing Foreign Key Inference v2** — `detect_implicit_relationships`'i (`app/schema/implicit_relationships.py`) PK-aware hale getiren sprint. Yeni saf `resolve_target_key(table)`: tek-kolonlu deklare PK → o kolon, composite PK → `None`, deklare PK yoksa `"id"` sonra `"<singular>_id"` konvansiyon fallback'i. Rule 1/2 artık hardcoded `"id"` yerine çözülmüş anahtarı hedefliyor (recall — `id` olmayan PK'ler artık yakalanıyor); Rule 3 yalnız hedef çözülmüş anahtarsa tetikleniyor (precision — spurious non-key eşleşmeler düştü). Confidence/reason string'leri korundu. Benchmark v5: `implicit_fk` `rule3_exact` 461/13024/56449 → 0 (scale 100/500/1000); `join_paths`/`context_selection`/`graph_backend` v4'e göre byte-identical (coupling yok). Gate yeşil. Bilinçli kapsam dışı: type-uyumluluk, config-driven eşikler, unique-ama-PK-olmayan hedefler, composite-PK çıkarımı, veri örneklemesi/value-overlap (TECH-DEBT §13). Full suite 2501 passed/9 skipped. `docs/SPRINT-PR-LOG.md` (PR #156) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.6** | **Schema Cache Invalidation** — `SchemaManager.load_schema`'nın eski `db_type`-only okuma predikatını içeriğe duyarlı bir fingerprint'le değiştiren sprint. Yeni saf `app/schema_cache_fingerprint.py`: `SCHEMA_CACHE_VERSION = "v1"` + `compute_cache_fingerprint(*, db_type, hidden_tables_raw, hidden_columns_raw, embedding_model, cache_version=...)` → sha256 (stdlib-only, deterministik). `load_schema` lock içinde güncel fingerprint'i hesaplayıp (embedding model ucuz okunur, build tetiklenmez) cache'teki `cache_fingerprint`'le karşılaştırıyor; uyuşmazlık/eksiklikte yeniden çıkarım yapılıyor (eski `db_type`-only kontrol subsumed). `hidden_tables`/`hidden_columns` config drift'i ve embedding-model değişikliği artık cache'i otomatik invalidate ediyor; fingerprint'siz eski cache bir kez yeniden çıkarılıp yeniden yazılıyor. Self-contained — yeni DB sorgusu yok. Lock/stampede/RAG/relationship-dressing değişmedi. Bilinçli kapsam dışı (TECH-DEBT §14): ham DB şema drift'i (→ 28.7 ile örtüşebilir), TTL invalidation, explicit invalidation endpoint/event, granüler embedding-only invalidation. Benchmark etkilenmedi, gate yeşil. Full suite 2509 passed/9 skipped. `docs/SPRINT-PR-LOG.md` (PR #157) |
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.7** | **Incremental Schema Sync** — 28.6'nın self-contained fingerprint'inin göremediği ham DB yapısal drift'ini (tablo/kolon/FK ekleme-kaldırma-değişim) kapatan sprint. Yeni saf `app/schema/schema_signature.py`: `SCHEMA_SIGNATURE_VERSION = "v1"` + `normalize_structure` (dialect-agnostic, sıra-bağımsız kanonik yapı) + `compute_schema_signature` (sha256) + `diff_structures` → `StructuralDrift` (added/removed tables, added/removed/changed columns, added/removed FKs). `SchemaManager`'a `_current_normalized_structure`/`_current_schema_signature` helper'ları eklendi; cache payload'ı yeni `schema_signature` alanını kazandı. `load_schema`'da **opt-in** yapısal drift kontrolü: yeni config `auto_schema_drift_check` **varsayılan KAPALI** (28.6 davranışı byte-for-byte korunur); açıldığında cache okunduğunda güncel signature cache'tekiyle karşılaştırılır, uyuşmazlıkta tam yeniden çıkarım+yeniden embedding tetiklenir. Yeni debug-gated router `app/api/schema_sync_api.py`: yan-etkisiz `GET /api/debug/schema/drift` (cache'i okur + taze signature hesaplar, ASLA `load_schema` çağırmaz) ve drift-aware `POST /api/debug/schema/sync?force=` (yalnız drift varsa veya `force=true` ise `force_refresh=True` ile yeniden inşa eder). **Benchmark etkilenmedi** (28.7 dört benchmark hedefine de `load_schema`'nın egzersiz edilen yoluna da dokunmuyor) — versiyon bump gerekmedi. **Bilinçli kapsam dışı (TECH-DEBT §15):** true per-table incremental re-extract/merge (drift'te hâlâ TAM yeniden çıkarım), granüler embedding-only re-index (→ 28.8), TTL/zaman-tabanlı invalidation (§14.2 hâlâ açık), ultra-ucuz tek-sorgulu drift sinyali (extract-reuse tercih edildi), yalnız yapısal drift (satır/veri-seviyesi drift yok), sync rebuild'i tüm-cache'dir, kısmi değil. TECH-DEBT §14.1/§14.3 ÇÖZÜLDÜ. Full suite 2537 passed/9 skipped. `docs/SPRINT-PR-LOG.md` (PR #158) |
| ▶️ **Sıradaki** | **Phase 9 · Sprint 28.8** | Embedding / RAG Re-Index Pipeline. `docs/PLANNED-SPRINTS.md` |
| 🗓️ **Planlanan** | **Phase 9 → 15** (Sprint 28.8 → 34.7) | `docs/PLANNED-SPRINTS.md` |

### Planlanan fazlar (durum)
| Phase | Tema | Sprint aralığı | Durum |
|---|---|---|---|
| 7 | Security & Governance | 26.x | ✅ Tamamlandı *(26.0–26.11)* |
| 8 | Observability & Debuggability | 27.x | ✅ Tamamlandı *(27.0–27.10 tamam; Phase 8 kapandı, sıradaki Phase 9 (28.0). 27.11 Tech-Debt Cleanup (bakım) ayrıca tamam — faz ilerletmez.)* |
| 9 | Large Schema Production Scale | 28.x | ▶️ Başladı *(28.0–28.7 tamam — sıradaki 28.8. 28.3.1 Tech-Debt Cleanup (bakım) ayrıca tamam — faz ilerletmez.)* |
| 10 | Real Database Adapter Layer | 29.x | 🗓️ Planlı *(25.8/25.9 stub'larının gerçeği)* |
| 11 | API / Backend Productization | 30.x | 🗓️ Planlı |
| 12 | UI / UX Production Layer | 31.x | 🗓️ Planlı |
| 13 | Deployment / Cloud / Ops | 32.x | 🗓️ Planlı |
| 14 | SaaS / Multi-Tenant Readiness | 33.x | 🗓️ Planlı |
| 15 | Desktop Readiness | 34.x | 🗓️ Planlı |

> **Feedback / öğrenen sistem notu:** `27.3 User Feedback Capture` feedback'i
> *toplar*; bunu *tüketen* minimal adım `27.9 Feedback Review → Rule Suggestion`
> olarak Phase 8'e eklendi. Tam "öğrenen sistem" (value index, trace mining,
> rule promotion) hâlâ daha ileri bir aşama; bkz. `docs/PLANNED-SPRINTS.md`.

---

## Backlog — tema bazlı özellik fikirleri

Aşağıdaki fikirler eski plandan taşınmıştır; ilgili faza işaret edilmiştir.

### Doğruluk / Retrieval
- **Değer Düzeyi Semantik RAG (Value-Level RAG):** Düşük kardinaliteli kolonların
  distinct değerleri indekslenir; "Marmara" → `region_code = 'MAR'` çevirisi
  prompt'a enjekte edilir. *(öğrenen sistem / feedback teması)*
- **Kurumsal Veri Sözlüğü RAG:** SAP/Oracle EBS teknik kısaltmalarında (MARA,
  KNA1) veri sözlüğü açıklamalarıyla semantik tohum arama. *(öğrenen sistem)*

### Graph / Join (→ Phase 9)
- **LLM Tabanlı Kenar Ağırlıklandırması:** Eşit ağırlıklı BFS yerine iş
  mantığına göre ağırlıklı Dijkstra/A* ile optimal join path.

### Execution (→ Phase 10)
- **Çoklu Veritabanı Paralel Sandbox Test:** Üretilen SQL'i read-only kopyada
  `EXPLAIN`/`LIMIT 1` ile çalıştırıp planı Critic'e iletme.
- **Sorgu Optimizasyon Tavsiyeleri:** `LIKE '%...%'` gibi full-scan riskleri için
  index önerileri.

### Güvenlik (→ Phase 7)
- **Şema Anonimleştirme (Zero-Knowledge):** İsimleri LLM'e göndermeden maskeleme
  (`MUSTERI_MAAS` → `T1_C4`), SQLGlot ile geri çevirme; KVKK/GDPR.
- **Rol Bazlı Şema Kısıtlama (RBAC):** Role göre tablo/kolon gizleme.
- **Lokal Edge LLM Desteği (Ollama / vLLM):** Çevrimdışı küçük kod modelleri.

### Performans & UX (→ Phase 9/11/12)
- **Semantik Önbellekleme:** Anlamca eşdeğer sorgu için doğrulanmış SQL'i
  pipeline'ı atlayarak ~100 ms'de döndürme.
- **Asenkron Paralel Çalıştırma:** BFS budama + Qdrant RAG aramalarını
  `asyncio.gather` ile paralel.
- **Parçalı Şema Enjeksiyonu (Lazy Loading):** İlk taslakta sadece tablo+PK;
  detayları agentic tool-calling ile çekme.
- **Doğal Dil ile SQL İzahı (XAI)** ve **Tek Tıkla Çalıştırma + Görselleştirme.**
