# Teknik Borç ve Geçici Çözümler (Tech Debt & Workarounds)

Bu dosya, projede karşılaşılan sorunları hızlıca çözmek için uygulanan geçici
yöntemleri (workarounds) ve teknik borç (technical debt) notlarını içerir.
İleride sistem mimarisi iyileştirilirken bu çözümler kalıcı yöntemlerle
değiştirilmelidir.

> Sürüm geçmişi için `CHANGELOG.md`, yol haritası için `ROADMAP.md` ve
> `docs/PLANNED-SPRINTS.md` dosyalarına bakın.

---

## 1. NVIDIA Batch Embedding API Token Limit Aşımı (22 Mayıs 2026) — ÇÖZÜLDÜ

**Hata Logu:**
`[SchemaEmbedding] Embedding indeksleme başarısız: NVIDIA Batch Embedding API Hatası 400: {"error":"Input length 1728 exceeds maximum allowed token size 512"}`

**Neden:**
NVIDIA NIM Embedding API'si (ve çoğu standart embedding modeli) metin başına
maksimum 512 token boyutunu kabul etmektedir. Şema indeksleme sırasında
(`backend/app/schema_embedding.py`), özellikle çok fazla kolonu olan tabloların
(örn: 100+ kolon) tüm kolon isimleri ve foreign key kısıtları birleştirilip
"semantic fingerprint" çıkarıldığında bu token limiti aşılmaktadır.

**Uygulanan Çözüm:**
`baai/bge-m3` modelinde yaşanan NVIDIA NIM sunucu çökmeleri (500 Error) sebebiyle,
varsayılan embedding modeli, daha geniş bağlam boyutunu destekleyen ve çok daha
stabil olan `nvidia/llama-nemotron-embed-1b-v2` ile değiştirildi. Qdrant'taki
vektör boyutu bu modele uygun olacak şekilde **2048** olarak ayarlandı. Karakter
kırpma (truncation) limiti `25000` karaktere çıkarılarak tüm tablo şemalarının
eksiksiz embedding işleminden geçmesi sağlandı; kolon veri tipleri de semantic
fingerprint'e dahil edildi.

**Tek doğru kaynak (kodla doğrulanmıştır):**
- Model: `nvidia/llama-nemotron-embed-1b-v2` — `backend/app/rag_manager.py:16`
- Vektör boyutu: `2048` — `backend/app/rag_manager.py:123`

> ⚠️ Not: `FEATURE.md` ve RAG dokümanlarında geçen `llama-3.2-nv-embedqa-1b-v2`
> ve `nvidia/embeddings-nv-embed-qa-4 (1024)` referansları **eskidir**; koddaki
> değer yukarıdaki gibidir. Bu dokümanlar güncellenmelidir.

**Gelecekte Yapılabilecek Geliştirmeler (Opsiyonel):**
- Tablolar indekslenirken bütün kolonların tek satıra sıkıştırılması yerine
  tabloları mantıksal alt parçalara (chunk) bölerek indeksleme (RAG için alt
  tablo stratejisi) düşünülmelidir.
- Büyük şemalarda kolon meta verileri ayrı node/vektör olarak tutulup
  hiyerarşik (Parent-Child Retriever) RAG mimarisi uygulanabilir.

---

## 2. D3 Graph UI Performans Limiti (maxNodesLimit = 5) — BÜYÜK ÖLÇÜDE ÇÖZÜLDÜ (2026-07-02 ara fix)

**Eski durum:** Tarayıcı çökmesini engellemek için `maxNodesLimit` varsayılan
olarak **5 tabloya** sınırlandırılmıştı; üstelik top-N seçimi *izole tablolar
dahil tüm tablolar* üzerinden yapılıp yalnızca iki ucu da seçimde kalan edge'ler
çizildiğinden, örnek şemada (2175 tablo / 93 FK) ilişkilerin yalnızca **3/93**'ü
görünüyordu. "Limitsiz" seçeneği ise 2073'ü tamamen izole olan 2175 node'u
render ederek tarayıcıyı kilitliyordu — donmanın asıl kaynağı buydu.

**Uygulanan çözüm (ara fix, 2026-07-02):** Node/edge seçim mantığı saf
`frontend/src/utils/graphSelection.ts` modülüne çıkarıldı. İzole (ilişkisiz)
tablolar artık **hiç çizilmiyor**; limit yalnızca bağlantılı tablolar arasında
uygulanıyor ve varsayılan `0 = tüm bağlantılı tablolar` oldu (örnek şemada 102
tablo + 93/93 ilişki, akıcı render). Graph paneli render istatistiği gösteriyor
("X/Y bağlantılı tablo · Z ilişki · N izole tablo gizlendi"). Test:
`frontend/tests/graphSelection.test.ts`.

**Kalan borç (Phase 12 · 31.x UI/UX Production Layer'a aday):** *Bağlantılı*
tablo sayısının da binlere ulaştığı şemalarda D3 force-directed SVG render yine
zorlanır; kalıcı çözüm için kademeli yükleme (progressive/virtualized
rendering), WebGL tabanlı graph kütüphanesi veya sunucu tarafı layout
hesaplaması değerlendirilmelidir. `Node Limiti` girişi bu senaryo için kaçış
kapısı olarak korunmuştur. Ayrıca frontend'de test framework yok;
`graphSelection` testleri şimdilik `node --experimental-strip-types` ile koşulan
tek dosyalık script'tir (vitest kurulumu ayrı bir kalem).

*İlgili Dosyalar:* `frontend/src/components/SchemaManager.vue`,
`frontend/src/utils/graphSelection.ts`, `frontend/tests/graphSelection.test.ts`

---

## 3. SKIPPED span'lerde `duration_ms` düşürülüyor (Sprint 27.1w) — AÇIK

**Sorun:**
`build_intent_span` ve `build_retrieval_span`, `result is None` erken-dönüş
dalında `TraceSpan(..., status=SKIPPED)` kuruyor ve kendilerine verilen
`duration_ms` argümanını **hiç kullanmıyor** — imzaları kabul etmesine rağmen
sessizce düşüyor.

**Etkisi:**
Canlı yolda intent extraction koşmadığı için INTENT span'i her zaman SKIPPED
olur; dolayısıyla `_stage_intent`'in ölçülen süresi (`intent_ms`) happy path'te
payload'a **inmez**. Süre yalnızca INTENT *hata* dalında (elle kurulan ERROR
span'i) taşınır. Aynı desen RETRIEVAL/SKIPPED için de geçerli.

**Neden şimdilik böyle:**
27.1w planının düzyazı kuralı (satır 187) "duration_ms: her builder'a
`stage_timings.get(<stage adı>)` verilir" diyor, ama planın kendi referans kodu
INTENT/SECURITY'ye geçmiyordu — plan kendi içinde çelişiyordu. Whole-branch
review bunu yakaladı; SECURITY tarafı düzeltildi (`build_security_span` artık
`duration_ms` alıyor ve SKIPPED dahil tüm dallarda taşıyor). INTENT/RETRIEVAL'ın
SKIPPED dalına dokunmak onaylanan fix kapsamı dışındaydı ve semantik bir soru
içeriyor: **koşmamış (SKIPPED) bir stage'e süre iliştirmek doğru mudur?**
`_stage_intent` duvar saati harcıyor ama intent *extraction* koşmuyor.

**Karar gerektiren nokta:**
Ya (a) SKIPPED span'ler de gerçek duvar saatini taşısın (planın düzyazı kuralı
birebir uygulanır), ya da (b) SKIPPED span'in süresiz olması sözleşmenin bir
parçası kabul edilip planın düzyazı kuralı düzeltilir. Şu an (b) fiilen
geçerli ama yazılı değil.

*İlgili Dosyalar:* `backend/app/trace/end_to_end_trace_builders.py:114-115`
(`build_intent_span`), `:146-147` (`build_retrieval_span`),
`backend/app/trace/live_trace_assembly.py`

---

## §4. Error taxonomy v2'nin ulaşamadığı sınırlar (Sprint 27.2) — AÇIK

Sprint 27.2 taksonomiyi tek registry'de topladı ama bilinçli olarak pipeline
katmanında durdu. Kalanlar:

1. **İş/API/frontend sınırı (27.2.1).** `result["error_code"]` üretiliyor ama
   `main.py:394-405` yalnız `result["error"]`'ı (serbest metin) `job.error_message`'a
   yazıyor. `JobDetailResponse` (`api/schemas.py:51-61`) kod alanı taşımıyor.
   Taksonomi bu sınırda tamamen yok oluyor.
2. **`api.ts` `detail` bug'ı (kullanıcı-görünür).** Frontend `errData.detail`
   okuyor (`api.ts:161,174,187`), envelope ise `{"error":{"code",...}}` yolluyor
   (`api/schemas.py:149-156`). `detail` hiçbir zaman yok → her API hata metni
   sessizce düşüyor, kullanıcı hardcoded fallback görüyor.
3. **`ExecutionSpanDetail.error_code` hâlâ beslenmiyor.** 27.0 spec §137 bu alanı
   "mevcut error taxonomy kodu" için açmıştı. Enum artık gerçek bir değer
   sağlayabiliyor ama canlı yolda EXECUTION span'i her zaman SKIPPED
   (`live_trace_assembly.py:170-171`) — besleyecek çağrı yolu yok.
4. **`classify_sql_error` hâlâ düzyazı ayrıştırıyor.** Sıra bug'ı düzeltildi ama
   mimari çözüm (validator'ların kod döndürmesi, mesaj eşlemek yerine)
   yapılmadı.
5. **`SQLFailureCategory`** (`evaluation/failure_analytics.py:39`) ayrı bir
   taksonomi olarak duruyor — eval'e özel, farklı eksen, birleştirilmedi.
6. **HTTP `code` sözlüğü** (`api/errors.py:13`) hâlâ status-türevi ve domain
   taksonomisiyle hiçbir şey paylaşmıyor.
7. **`retryable` ekseni** registry'de yok; `EmbeddingRetryableError`
   (`retrieval/embedding_pipeline.py:18`) onu ayrı bir hiyerarşide yeniden icat
   etmiş durumda. Registry'ye alan eklemek kırıcı değildir — retry mantığı
   gelen sprint'te birleştirilebilir.
8. **`details["error_type"]`** (`sql_execution_errors.py:52`) bir Python sınıf
   adı taşıyor, taksonomi kodu değil. Ad çakışması kafa karıştırıcı; yeniden
   adlandırmak kapsam dışıydı.
9. **Geliştirme trace DB'si migrate edilmedi.** `backend/data/nl2sql_traces.db`
   gitignore'da; eski satırlar v1 kod adlarını taşır ve `?error_type=` filtresiyle
   eşleşmez. Kabul edilen maliyet.
