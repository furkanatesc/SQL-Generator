# SQLGen — Yol Haritası (ROADMAP)

Bu dosya yol haritasının **tek giriş noktasıdır**. Faz bazlı detaylı mimari
kararlar `docs/architecture/` altındadır ve kanonik kaynaktır:

- [`docs/architecture/v1-production-plan.md`](docs/architecture/v1-production-plan.md) — Controlled Production Baseline
- [`docs/architecture/v2-feedback-loop.md`](docs/architecture/v2-feedback-loop.md) — Feedback ile Öğrenen Sistem
- [`docs/architecture/v3-graphrag-ppr.md`](docs/architecture/v3-graphrag-ppr.md) — GraphRAG / PPR / Dynamic Subgraph
- [`docs/architecture/v4-enterprise.md`](docs/architecture/v4-enterprise.md) — Enterprise-Grade Platform
- [`docs/architecture/v5-productization.md`](docs/architecture/v5-productization.md) — Productization (API / UI / Deployment)
- [`docs/architecture/v6-saas-desktop.md`](docs/architecture/v6-saas-desktop.md) — SaaS & Desktop Readiness

Tamamlanan işler için `CHANGELOG.md` ve `docs/SPRINT-PR-LOG.md`, ileriye dönük
detaylı sprint planı için `docs/PLANNED-SPRINTS.md` (Phase 7–15 · Sprint
25.8 → 34.7), teknik borç için `docs/TECH-DEBT.md`.

> `SPRINTHARITASI.txt` ve `senioryolharitası.txt` eski/kişisel notlardır ve bu
> dosya tarafından **geçersiz kılınmıştır** (arşivlenebilir).

---

## Şu an neredeyiz? (You are here)

Son durum: **v1 baseline ilan edildi; takım v3'e ait execution-accuracy
değerlendirme iskelesini kuruyor — ancak v2 (feedback loop) atlanmış durumda.**

| Faz | Tema | Durum | Not |
|-----|------|-------|-----|
| **v1** | Production Baseline | 🟢 Kapandı | 2026-06-05'te "release ready" ilan edildi (#81); `v1.0.0` tag'i `9907cd3`'e atıldı (2026-06-18). RC kanıtının ölü commit'i `5ce60ae` ile düzeltildi (metrikler UNVERIFIED). Kalan iz: `CandidateScorer`/`BoundedGraphPruner` kodda farklı isimde/eksik. |
| **v2** | Feedback Loop | ⏸️ Ertelendi | Trace Mining, Pending Rules, LLM Suggestion, **Value Index**, QueryIntentClassifier, Feedback UI — hiçbiri kodda yok. **Bilinçli olarak ertelendi** (2026-06-18): execution-accuracy (v3) hattı önceliklendirildi. Tekrar ele alınacak; bkz. `docs/architecture/v2-feedback-loop.md`. |
| **v3** | GraphRAG / PPR | 🟡 Sıra dışı başladı | Yalnızca execution-accuracy değerlendirme altyapısı kuruldu (`connection_abstraction`, `multi_database_execution`, execution orchestrator). **PostgreSQL adapter STUB** (`NOT_IMPLEMENTED`). PPR, column-level pruning, execution-guided repair, multi-candidate **yok**. *(Plan: Phase 9–10)* |
| **v4** | Enterprise | ⚪ Başlamadı | Multi-tenant, RBAC, PII redaction, governance — yok. *(Plan: Phase 7–8 + Phase 14'ün güvenlik kısmı)* |
| **v5** | Productization | ⚪ Başlamadı | Public API, production UI, deploy/ops — yok. *(Plan: Phase 11–13)* |
| **v6** | SaaS & Desktop | ⚪ Başlamadı | Org/workspace, billing, metering, desktop packaging — yok. *(Plan: Phase 14–15)* |

### Sıralama kararı (güncel)
Son ~6 sprint (20–25) v3'e ait değerlendirme/execution iskelesini kurarken
**v2'nin tüm feedback-loop çıktıları atlandı**. Bu durum bilinçli bir karara
bağlandı:
1. ✅ **v1 resmen kapatıldı**: `v1.0.0` tag'i atıldı + RC kanıtı `5ce60ae` ile
   düzeltildi (2026-06-18).
2. ⏭️ **v3 hattı önceliklendirildi**: PostgreSQL adapter stub'ını gerçek
   (read-only) implementasyona çevirmek ve execution-accuracy harness'ını
   bağlamak (Phase 9–10).
3. ⏸️ **v2 (feedback-loop / Value Index) ertelendi**: v3 execution hattı
   stabilleşene kadar beklemeye alındı. İptal değil, ertelendi.

---

## Backlog — Faz bazlı özellik fikirleri

Aşağıdaki fikirler eski `SOON.md`'den taşınmış olup ilgili mimari fazlara
eşlenmiştir. Detaylı kabul kriterleri için `docs/architecture/` dosyalarına bakın.

### v2 — Feedback ile Öğrenen Sistem
- **Değer Düzeyi Semantik RAG (Value-Level RAG):** Düşük kardinaliteli kolonların
  distinct değerleri Qdrant'ta `value_dictionary` koleksiyonunda indekslenir;
  "Marmara" → `sales.region_code = 'MAR'` gibi değer çevirisi prompt'a enjekte
  edilir.
- **Kurumsal Veri Sözlüğü RAG:** SAP/Oracle EBS gibi teknik kısaltmalı şemalarda
  (MARA, KNA1) veri sözlüğü açıklamaları vektörleştirilir; tohum tablo aramasında
  semantik eşleşme kullanılır.
- **Doğal Dil ile SQL İzahı (XAI):** Üretilen SQL'in altına teknik olmayan
  yöneticiler için kısa açıklama eklenir.

### v3 — GraphRAG / PPR / Optimizasyon
- **LLM Tabanlı Kenar Ağırlıklandırması:** Eşit ağırlıklı BFS yerine, iş
  mantığına göre ağırlıklandırılmış Dijkstra/A* ile optimal join path.
- **Çoklu Veritabanı Paralel Sandbox Test:** Üretilen SQL'i read-only kopyada
  `EXPLAIN`/`LIMIT 1` ile çalıştırıp execution plan/performans verisini Critic'e
  iletme. *(Mevcut execution-accuracy iskelesi bunun temelidir.)*
- **Sorgu Optimizasyon Tavsiyeleri:** `LIKE '%...%'` gibi full-table-scan
  riskleri için DBA seviyesinde index önerileri.

### v4 — Enterprise & Güvenlik
- **Şema Anonimleştirme (Zero-Knowledge):** Tablo/kolon isimlerini LLM'e
  göndermeden önce maskeleme (`MUSTERI_MAAS` → `T1_C4`), SQLGlot ile geri çevirme;
  KVKK/GDPR uyumu.
- **Rol Bazlı Şema Kısıtlama (RBAC):** Kullanıcı rolüne göre tablo/kolon gizleme.
- **Lokal Edge LLM Desteği (Ollama / vLLM):** Çevrimdışı küçük kod modelleri
  (Qwen-2.5-Coder-7B, Llama-3-8B) desteği.

### Süreklilik — Performans & UX (faz-bağımsız)
- **Semantik Önbellekleme:** Anlamca eşdeğer sorgular için doğrulanmış SQL'i
  pipeline'ı atlayarak ~100 ms'de döndürme.
- **Asenkron Paralel Çalıştırma:** BFS budama ile Qdrant RAG aramalarını
  `asyncio.gather` ile paralel hale getirme.
- **Parçalı Şema Enjeksiyonu (Lazy Schema Loading):** İlk taslakta sadece tablo
  isimleri + PK gönderip, LLM'in agentic tool-calling ile detay çekmesi.
- **Tek Tıkla Sorgu Çalıştırma ve Görselleştirme:** Electron'dan read-only
  (`LIMIT 100`) çalıştırma + interaktif tablo/grafik önizleme.
