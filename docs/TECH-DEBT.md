# Teknik Borç ve Geçici Çözümler (Tech Debt & Workarounds)

Bu dosya, projede karşılaşılan sorunları hızlıca çözmek için uygulanan geçici
yöntemleri (workarounds) ve teknik borç (technical debt) notlarını içerir.
İleride sistem mimarisi iyileştirilirken bu çözümler kalıcı yöntemlerle
değiştirilmelidir.

> Sürüm geçmişi için `CHANGELOG.md`, yol haritası için `ROADMAP.md` ve
> `docs/architecture/` dosyalarına bakın.

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

## 2. D3 Graph UI Performans Limiti (maxNodesLimit = 5) — AÇIK

**Durum:** Tarayıcı çökmesini engellemek için `SchemaManager.vue`'da
`maxNodesLimit` varsayılan olarak **5 tabloya** sınırlandırılmıştır
(`frontend/src/components/SchemaManager.vue:28`). UI üzerinden manuel olarak
değiştirilebilir (`0 = limitsiz`).

**Teknik borç:** Bu limit, "800+ tablolu kurumsal şema" iddiasıyla çelişir. Büyük
şemalarda D3 force-directed graph render'ı tarayıcıyı kilitlemektedir. Kalıcı
çözüm için kademeli yükleme (progressive/virtualized rendering), WebGL tabanlı
graph kütüphanesi veya sunucu tarafı layout hesaplaması değerlendirilmelidir.

*İlgili Dosya:* `frontend/src/components/SchemaManager.vue`
