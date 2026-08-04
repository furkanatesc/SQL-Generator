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
| ✅ **Tamamlandı** | **Phase 9 · Sprint 28.0** | **Large Schema Benchmark Suite** — Phase 9'un ilk sprint'i, **Phase 9 başladı**. Yeni `backend/benchmarks/` paketi (dev/CI aracı; hiçbir `app/` dosyası değişmedi): seeded sentetik şema üreteci (100/500/1000/2000 tablo) + frozen metrik sözleşmesi + 4 REUSED prodüksiyon hedefi için determinist metrik çıkarıcıları (`from_legacy_schema`/`find_join_paths`/`detect_implicit_relationships`/`select_schema_context`) + 27.10 desenini izleyen `compare_benchmark` + enjekte-clock'lu runner (`wall_ms` yalnız bilgi amaçlı) + CLI (`--gate`/`--update-baseline`, exit 0/1/2) + seeded committed baseline. İç patlama sayaçları/CI perf-gate/NetworkX pruner/embedding benchmark'ları bilinçli olarak 28.1+'a ertelendi (`docs/TECH-DEBT.md` §12). `docs/SPRINT-PR-LOG.md` (PR #TBD) |
| ▶️ **Sıradaki** | **Phase 9 · Sprint 28.1** | Schema Graph Performance Profiling. `docs/PLANNED-SPRINTS.md` |
| 🗓️ **Planlanan** | **Phase 9 → 15** (Sprint 28.1 → 34.7) | `docs/PLANNED-SPRINTS.md` |

### Planlanan fazlar (durum)
| Phase | Tema | Sprint aralığı | Durum |
|---|---|---|---|
| 7 | Security & Governance | 26.x | ✅ Tamamlandı *(26.0–26.11)* |
| 8 | Observability & Debuggability | 27.x | ✅ Tamamlandı *(27.0–27.10 tamam; Phase 8 kapandı, sıradaki Phase 9 (28.0). 27.11 Tech-Debt Cleanup (bakım) ayrıca tamam — faz ilerletmez.)* |
| 9 | Large Schema Production Scale | 28.x | ▶️ Başladı *(28.0 tamam — sıradaki 28.1)* |
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
