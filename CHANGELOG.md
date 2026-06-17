# Geçici Çözümler (Workarounds)

Bu dosya, projede karşılaşılan sorunları hızlıca çözmek için uygulanan geçici yöntemleri (workarounds) ve teknik borç (technical debt) notlarını içerir. İleride sistem mimarisi iyileştirilirken bu çözümler kalıcı yöntemlerle değiştirilmelidir.

## 1. NVIDIA Batch Embedding API Token Limit Aşımı (22 Mayıs 2026)

**Hata Logu:** 
`[SchemaEmbedding] Embedding indeksleme başarısız: NVIDIA Batch Embedding API Hatası 400: {"error":"Input length 1728 exceeds maximum allowed token size 512"}`

**Neden:** 
NVIDIA NIM Embedding API'si (ve çoğu standart embedding modeli) metin başına maksimum 512 token boyutunu kabul etmektedir. Şema indeksleme sırasında (`backend/app/schema_embedding.py`), özellikle çok fazla kolonu olan tabloların (örn: 100+ kolon) tüm kolon isimleri ve foreign key kısıtları birleştirilip "semantic fingerprint" çıkarıldığında bu karakter limiti aşılmaktadır.

**Uygulanan Kalıcı Çözüm:**
NVIDIA API üzerinden kullanılan varsayılan embedding modeli, `baai/bge-m3` modelinde yaşanan NVIDIA NIM sunucu çökmeleri (500 Error) sebebiyle, **dev bağlam boyutunu destekleyen (130K+ token)** ve çok daha stabil olan NVIDIA'nın kendi endüstri standardı modeli **`nvidia/llama-nemotron-embed-1b-v2`** ile değiştirildi.
Qdrant veritabanındaki vektör boyutu da bu modele uygun olacak şekilde orijinal hali olan `2048` olarak güncellendi.
Önceki geçici karakter kırpma (truncation) limitleri `25000` karaktere çıkarılarak tüm tablo şemalarının eksiksiz şekilde embedding işleminden geçmesi sağlandı. Aynı zamanda kolon veri tipleri de semantic fingerprint'e dahil edilerek yapay zekanın tabloyu anlama kapasitesi (context) maksimuma çıkarıldı.

*İlgili Dosyalar:* 
- `backend/app/rag_manager.py` (Model ve vektör boyutu değişimi)
- `backend/app/schema_embedding.py` (Karakter limitinin 25000'e çıkarılması)

**Gelecekte Yapılabilecek Geliştirmeler (Opsiyonel):**
- Tablolar embedding için indekslenirken, bütün kolonların tek satıra sıkıştırılması yerine tabloları mantıksal alt parçalara (chunk) veya doküman bloklarına bölüp indeksleme işlemi (örneğin RAG için alt tablolar stratejisi) düşünülmelidir. 
- Büyük şemalarda semantic search için kolon meta verileri veritabanında ayrı node'lar/vektörler olarak tutulabilir ve hiyerarşik (Parent-Child Retriever) RAG mimarisi uygulanabilir.
- **D3 Graph UI Performans�**: Taray�c� ��kmesini engellemek i�in SchemaManager.vue'da \maxNodesLimit\ varsay�lan olarak 5 tabloyayla s�n�rland�r�lm��t�r. UI'da manuel olarak de�i�tirilebilir.
