# Changelog

Bu projedeki tüm önemli değişiklikler bu dosyada belgelenir.

Format [Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) temel alınır;
sürümleme mantığı `docs/architecture/` altındaki v1–v4 olgunlaşma fazlarına göre
düzenlenmiştir. Geçici çözümler ve teknik borç için `docs/TECH-DEBT.md`, ileriye
dönük plan için `ROADMAP.md` dosyalarına bakın.

> ℹ️ **Sürüm etiketi notu:** v1.0.0 `9907cd3` (#81) commit'ine annotated git
> tag olarak **uygulandı** (2026-06-18). Geçmiş kayıt: RC doğrulama dokümanında
> atıf yapılan eski `2f9e7e6` commit'i repoda yoktu; gerçek RC kanıt commit'i
> `5ce60ae` (#80) ile düzeltildi ve oradaki "%96.5 accuracy / 500 query" gibi
> metrikler **UNVERIFIED** olarak işaretlendi (gerçek bir CI çalışmasıyla
> yeniden bağlanmalıdır).

---

## [Unreleased] — Sprint 20–25 · v2/v3 hattı (2026-06-05 → günümüz)

v1 baseline'ı sonrası retrieval, prompting ve execution-accuracy altyapısının
sözleşme (contract) odaklı geliştirilmesi. Bu fazdaki çıktıların çoğu hâlâ
contract/stub seviyesindedir; durum için `ROADMAP.md`'deki tabloya bakın.

### Added
- **Şema sözleşmesi ve ilişki motoru** (Sprint 20): şema sözleşmesi ve cross-db
  tutarlılık testleri, explicit FK sözleşmesi, örtük (implicit) ilişki tespiti
  sağlamlaştırması, graph traversal ve şema serileştirme (#82–#87).
- **Retrieval / context selection** (Sprint 21): şema context seçiminin
  sağlamlaştırılması, context selector entegrasyonu, şema özetleme sözleşmesi,
  embedding pipeline güvenilirliği, top-k retrieval sözleşmesi, context ranking,
  token budget yöneticisi (#88–#98).
- **Intent ve prompt planlama** (Sprint 22): intent extraction sözleşmesi,
  intent→context köprüsü, prompt planlama/rendering sözleşmeleri, SQL üretimi
  girdi derlemesi, SQL generation provider sınırı (#99–#104).
- **Prompt builder v2** (Sprint 23): few-shot örnek seçimi (deterministik ve
  dinamik), yapılandırılmış çıktı (structured output) üretimi, self-check
  üretimi (#105–#109).
- **Execution accuracy altyapısı** (Sprint 24–25): Golden Dataset V2 sözleşmesi
  ve loader, `SQLExecutionAccuracyHarness` + comparator, failure analytics
  sözleşmesi, eval gate aggregator, regression dashboard sözleşmesi, çoklu
  veritabanı execution sözleşmesi, connection abstraction katmanı,
  connection-aware execution planner ve orchestrator (#110–#121).

### Known limitations
- **PostgreSQL adapter yalnızca stub'dur** (`backend/app/evaluation/postgres_adapter.py`):
  her çağrıya `NOT_IMPLEMENTED` döner ve capability sözleşmesi canlı/driver/network
  execution'ı aktif olarak yasaklar. Gerçek execution henüz yoktur.
- v2 mimari planındaki feedback-loop çıktıları (Trace Mining, Pending Rules,
  Value Index, Feedback UI) henüz başlamadı.

---

## [1.0.0] — 2026-06-05 · Controlled Production Baseline

Patlamayan, debug edilebilen ve ölçülebilen ilk production baseline'ı.
Hedef "çok akıllı sistem" değil; her kararı izlenebilir güvenli sistemdi
(bkz. `docs/architecture/v1-production-plan.md`).

### Added
- **Release hazırlığı** (Sprint 16–19): production runbook ve smoke gate, V1
  release candidate gate, RC doğrulama kanıtı ve release readiness ilanı
  (#78–#81).
- **Observability** (Sprint 18): request logging, request correlation,
  performance telemetry, readiness/startup diagnostics, startup config
  doğrulama gate'i (#73–#77).
- **API yüzeyi dondurma** (Sprint 17): API surface envanteri + OpenAPI snapshot,
  hata yanıtı ve response envelope şeması dondurma, API key/debug erişim
  sözleşmesi, HTTP status semantiği, sözleşme yeniden üretim araçları (#68–#72).
- **Runtime altyapısı** (Sprint 16): `pydantic-settings` ile merkezî runtime
  ayarları, güvenli health diagnostics, startup validation warnings, backend
  Docker baseline + container runtime smoke testi, ortam değişkeni sözleşmesi,
  release verification checklist (#59–#67).
- **Trace ve debug** (Sprint 14–15): `TraceStore` arayüzü + `InMemoryTraceStore`
  ve `SQLiteTraceStore`, debug trace API endpoint'leri (strict DTO, validation,
  credential redaction); Golden NL2SQL Eval Harness, kolon-düzeyi eval
  kontrolleri, eval failure reporting (#52–#58).
- **Read-only SQL execution guard'ları** (Sprint 12): read-only execution
  sandbox, query timeout, row limit guard, sonuç şekli doğrulama ve execution
  hata taksonomisi (#47–#50).
- **API sözleşmeleri** (Sprint 11): standart API hata yanıtı, pagination/query
  parametre sözleşmesi, job filter/sort sözleşmeleri (#42–#46).
- **Graph pruning mimarisi**: kabul testleriyle kilitlenen graph budama
  mimarisi; `GraphBackend` arayüzü ve `NetworkXGraphBackend` (#51).

### Changed
- Şema budama (graph traversal/hub/budget) mantığı `schema_pruner`'dan ayrı
  `schema_graph/` backend modüllerine taşındı (Sprint 2 refactor).

### Fixed
- SQL guardrail'ı: tehlikeli komut fonksiyonlarının reddi, guardrail hatasında
  üretilen SQL'in sanitize edilmesi, pipeline guardrail hatasında fail-fast
  davranışı (#12–#16).

---

## [0.x] — Temel altyapı (2026-05-20 → 2026-05-25) · Sprint 2–4

### Added
- İlk konsol/pipeline iskeleti: schema lexicon, trace store ve SQL validator;
  TextNormalizer, tokenizer ve generic token yönetimi, gerçek RAG skor eşiği ve
  tracing, CandidateStore + sinyal toplama, hibrit synonym repository, mini
  golden query ve regression testleri (Patch 0–5).
- Graph modülü ayrıştırması: `schema_graph/backend.py`,
  `schema_graph/networkx_backend.py`, traversal policy (Sprint 2).
- LLM provider sınırı: provider arayüz sözleşmesi, SQL generation request/response
  sözleşmesi, deterministik fake provider seam, manuel NVIDIA provider adaptörü
  (#4–#7).
- SQL dialect doğrulama sözleşmesi ve read-only guardrail sözleşmeleri (#9–#13).
- CI'da smoke eval; eval sözleşmelerinin kilitlenmesi (#1–#3).

---

[Unreleased]: https://github.com/furkanatesc/SQL-Generator/compare/main...HEAD
