# SQLGen — Gelecek Yol Haritası (SOON.md)

Bu belgede, SQLGen platformunun gelecekteki kurumsal yeteneklerini artırmak, Text-to-SQL doğruluğunu en üst seviyeye çıkarmak ve sistemi devasa kurumsal veritabanlarına entegre etmek için planlanan gelecek yol haritası ve teknik entegrasyon tasarımları yer almaktadır.

---

## Planlanan Entegrasyonlar ve Özellikler

### 1. Değer Düzeyi Semantik RAG (Value-Level RAG)

Mevcut şema pruner algoritmamız tablo ve kolon adlarını çok iyi eşleştirmesine rağmen, veritabanının içindeki satır bazlı değerleri doğrudan bilemez. Kullanıcıların doğal dil sorgularında kullandığı filtreler ile veritabanındaki gerçek kayıtlar arasındaki uyumsuzlukları gidermek için Değer Düzeyi RAG altyapısı planlanmaktadır.

#### Teknik Tasarım ve Çalışma Prensibi:
- **Veri Taraması ve İndeksleme:** Düşük kardinaliteli (low-cardinality) kolonlar (Örn: Ülkeler, Bölgeler, Kategori İsimleri, Müşteri Segmentleri) periyodik olarak taranır. Kolonlardaki benzersiz (distinct) değerler alınarak Qdrant vektör veritabanında ayrı bir value_dictionary koleksiyonunda indekslenir.
- **Semantik Yakalama:** Kullanıcı "Marmara bölgesindeki satışları göster" dediğinde, sorgudaki "Marmara" kelimesi RAG üzerinde aranır. 
- **Eşleme ve Çeviri:** Arama sonucunda "Marmara" kelimesinin, region_code kolonundaki "MAR" değeriyle yüksek oranda eşleştiği tespit edilir.
- **Prompt Enjeksiyonu:** LLM Yazar Ajanına giden prompt içerisine dinamik bir çeviri ipucu eklenir:
  ```markdown
  [Value Translation Hint]
  - Kullanıcının belirttiği "Marmara" terimi, "sales.region_code" kolonundaki "MAR" değeri ile eşleşmektedir. Sorguda bu filtreyi uygulayın.
  ```
- **Sonuç:** Kullanıcının veritabanı kodlamalarını bilmesine gerek kalmaz; jargonlar, yazım hataları veya kısaltmalar sistem tarafından arka planda otomatik olarak çözülerek sorguya tam doğru filtre yansıtılır.

---

### 2. Kurumsal Veri Sözlüğü RAG (Enterprise Data Dictionary RAG)

Özellikle büyük ERP sistemlerinde (örneğin SAP veya Oracle EBS) tablo ve kolon isimleri tamamen teknik kısaltmalardan (Örn: SAP'ta MARA malzeme ana verisi, KNA1 müşteri ana verisi) oluşur. Bu tür kurumsal şemalarda doğrudan kelime eşlemesi çalışmaz.

#### Teknik Tasarım ve Çalışma Prensibi:
- **Veri Sözlüğü Entegrasyonu:** Kurumun teknik veri sözlüğü (Data Dictionary) sisteme yüklenir. Tabloların ve kolonların teknik açıklamaları (Örn: MARA -> "Malzeme Ana Veri Tablosu - Malzeme numarası, tipi ve üretim verilerini içerir") RAG üzerinde vektörleştirilir.
- **Semantik Tohum Arama:** Şema budama modülü tohum tablo araması yaparken, eğer doğrudan kelime/token eşleşmesi bulamazsa, soruyu Kurumsal Veri Sözlüğü RAG sisteminde aratır.
- RAG, kullanıcının "Ürünler" kelimesiyle MARA açıklamasının semantik olarak en yakın eşleşme olduğunu bulur ve BFS algoritmasına başlangıç tohumu olarak MARA tablosunu teslim eder.
- **Sonuç:** Anlamsız tablo/kolon adlarına sahip devasa legacy sistemlerde dahi hatasız bir şekilde Text-to-SQL dönüşümü gerçekleştirilir.

---

### 3. Çoklu Veritabanı Paralel Sandbox Test Entegrasyonu

Üretilen SQL sorgusunun doğruluğundan emin olmak için yalnızca sentaks analizi (SQLGlot AST) yapmakla kalmayıp, sorguyu geçici bir Sandbox (Kum Havuzu) ortamında çalıştıran bir doğrulama katmanı eklenecektir.

#### Teknik Tasarım ve Çalışma Prensibi:
- Üretilen SQL sorgusu, hedef veritabanının salt okunur (Read-Only) bir kopyası veya şema kopyası üzerinde paralel olarak EXPLAIN veya LIMIT 1 komutlarıyla test edilir.
- Veritabanından dönen execution plan hataları veya performans verileri (Index kullanımı, CPU maliyeti) Eleştirmen Ajana iletilir.
- Eleştirmen Ajan, sorguyu sadece çalışabilir değil, aynı zamanda en hızlı çalışacak şekilde yeniden düzenler.

---

### 4. LLM Tabanlı Grafik Kenar Ağırlıklandırması (Reasoning Edge Weighting)

BFS algoritması şu anda tüm join yollarını eşit ağırlıkta kabul ederek en kısa yolu bulur. Ancak bazı durumlarda daha uzun ama iş mantığına daha uygun join yolları tercih edilmelidir.

#### Teknik Tasarım ve Çalışma Prensibi:
- İlişki grafiğindeki kenarlara (edges) dinamik ağırlıklar verilir.
- LLM, sorgu amacına göre hangi tablolar arasındaki ilişkilerin iş mantığına daha yakın olduğunu analiz ederek ilişki ağırlıklarını anlık olarak günceller.
- BFS algoritması yerine en kısa yol için Dijkstra veya A* (A-Star) algoritması kullanılarak, iş kuralları açısından en mantıklı birleşim yolu (Optimal Join Path) seçilir.

---

### 5. Kurumsal Güvenlik ve Uyumluluk (Enterprise B2B Odaklı Ürünleştirme)

Kurumsal şirketler (Banka, Telekom, Sağlık) veritabanı şemalarını veya verilerini bulut tabanlı yapay zeka modellerine göndermekten her zaman çekinirler. Bu endişeleri tamamen ortadan kaldıracak güvenlik özellikleri geliştirilecektir.

#### Teknik Tasarım ve Çalışma Prensibi:
- **Şema Anonimleştirme (Schema Obfuscation):** LLM'e gönderilmeden önce tablo ve kolon isimlerini anında maskeleyen (örneğin MUSTERI_MAAS kolonunu T1_C4 yapan) bir ara katman yazılacaktır. LLM, T1_C4 üzerinden SQL üretir ve SQLGlot katmanı bunu tekrar orijinal MUSTERI_MAAS ismine çevirir. Bu özellik, ürünü tam anlamıyla KVKK/GDPR uyumlu bir "Zero-Knowledge" platformu haline getirir.
- **Lokal Edge LLM Desteği (Ollama / vLLM):** Sadece NVIDIA NIM değil, müşterinin kendi sunucusunda çevrimdışı çalışan açık kaynaklı daha küçük kod modellerine (Örn: Qwen-2.5-Coder-7B veya Llama-3-8B) bağlanma seçeneği sunulacaktır. Güvenlik endişesi olan kurumlara ürünü ulaştırmanın en büyük anahtarı bu yerel çalışma yeteneğidir.
- **Rol Bazlı Şema Kısıtlama (RBAC):** Pazarlama departmanından bir analistin, "İnsan kaynakları maaşlarını getir" diyememesi gerekir. SchemaManager içerisine kullanıcı rollerine göre tabloları gizleyen yetkilendirme ve kısıtlama güvenlik katmanı eklenecektir.

---

### 6. Mimari ve Performans Optimizasyonları (Hız ve Maliyet)

Mevcut pipeline oldukça sağlam çalışmakla birlikte, dış API maliyetlerini düşürmek ve yanıt sürelerini daha da hızlandırmak adına aşağıdaki optimizasyonlar planlanmaktadır.

#### Teknik Tasarım ve Çalışma Prensibi:
- **Semantik Önbellekleme (Semantic Caching):** RAG yapısı önbellekleme için kullanılacaktır. Kullanıcı "Geçen ayki satışlar ne kadardı?" dediğinde, daha önce başka bir kullanıcı "Önceki ayın satış toplamları" dediyse ve bu önbellekte varsa, LLM pipeline'ı ve budama algoritmaları tamamen atlanarak (bypass) önceden doğrulanmış SQL 100 milisaniye içinde dönecektir.
- **Asenkron Paralel Çalıştırma:** Mevcut akışta ardışık çalışan Şema Budama (BFS) ve Qdrant İş Kuralları (RAG) aramaları, asyncio.gather ile paralel hale getirilerek işlem süreleri anında saniyeler bazında kısaltılacaktır.
- **Parçalı Şema Enjeksiyonu (Lazy Schema Loading):** LLM'den ilk taslağı alırken sadece tablo isimleri ve birincil anahtarlar gönderilecek; LLM'in ihtiyaç duyması halinde "Şu tabloların detayını ver" diyerek (Agentic Tool Calling mantığıyla) verileri asenkron çekmesi sağlanacaktır. Bu yapı token maliyetlerini ciddi oranda düşürecektir.

---

### 7. Kullanıcı Deneyimi ve Ayrıcalıklı Özellikler (Wow Factor)

Yalnızca SQL üretmek teknik ekipleri tatmin etse de, son kullanıcıları ve iş birimlerini tam anlamıyla etkilemek için son kullanıcı odaklı veri görselleştirme deneyimleri eklenecektir.

#### Teknik Tasarım ve Çalışma Prensibi:
- **Doğal Dil ile SQL İzahı (Explainable AI - XAI):** Üretilen karmaşık SQL'in altına, teknik olmayan yöneticiler için kısa bir Türkçe veya İngilizce çeviri eklenecektir: "Bu sorgu Müşteriler ve Siparişler tablolarını birleştirerek, 2023 yılından sonraki aktif müşterileri filtrelenmiş olarak getirmektedir." Bu şeffaflık kurum içi güveni artırır.
- **Tek Tıkla Sorgu Çalıştırma ve Görselleştirme:** Üretilen hatasız SQL sadece metin olarak bırakılmayacaktır. Electron uygulaması üzerinden veritabanına doğrudan bağlanılarak sorgu (güvenlik için LIMIT 100 kısıtıyla) anında çalıştırılacak ve sonuç interaktif bir veri tablosu veya Pivot/Bar Chart olarak "Veri Önizleme" sekmesinde ekrana basılacaktır.
- **Sorgu Optimizasyon Tavsiyeleri:** SQLGlot üzerinden geçen sorgularda LIKE '%...' kullanımı gibi performans darboğazları tespit edildiğinde, arayüzde "Bu sorgu Full Table Scan yapabilir, ilgili kolona Index eklenmesi önerilir" gibi DBA seviyesinde gelişmiş tavsiyeler verilecek, ürün devasa bir teknik otorite konumuna yükseltilecektir.
