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
| ✅ **Tamamlandı** | Sprint 0 → **26.5** | `v1.0.0` yayınlandı (tag `9907cd3`, 2026-06-18). Phase 6 (adapter stub'ları, #125/#126) kapandı; **Phase 7 devam ediyor** — 26.0 Permission Policy + 26.1 Tenant/Workspace Boundary + 26.2 Read-Only Enforcement + 26.3 Query Risk Classifier + 26.4 Sensitive Table/Column Policy + 26.5 PII/PHI Detection tamam. `docs/SPRINT-PR-LOG.md` |
| ▶️ **Sıradaki** | **Phase 7 · Sprint 26.6** | Audit Event Contract (`docs/PLANNED-SPRINTS.md`) |
| 🗓️ **Planlanan** | **Phase 7 → 15** (Sprint 26.4 → 34.7) | `docs/PLANNED-SPRINTS.md` |

### Planlanan fazlar (durum)
| Phase | Tema | Sprint aralığı | Durum |
|---|---|---|---|
| 7 | Security & Governance | 26.x | ▶️ Devam ediyor *(26.0–26.5 tamam)* |
| 8 | Observability & Debuggability | 27.x | 🗓️ Planlı |
| 9 | Large Schema Production Scale | 28.x | 🗓️ Planlı |
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
