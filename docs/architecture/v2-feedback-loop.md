# v2 — Feedback ile Öğrenen Sistem

## Amaç
Sistem artık sadece statik kurallarla çalışmayacak. Trace kayıtlarından ve kullanıcı/hata feedback’inden öğrenmeye başlayacak.
Dikkat: LLM runtime karar verici olmayacak, önerici olacak. İnsan onayı ile kurallar aktifleşecek.

## Kapsam
1. Trace Mining
2. Pending Rule System
3. LLM-Assisted Rule Suggestion
4. Value Index
5. Query Intent Classifier
6. Feedback UI / Debug UI

## Çıktılar
- Trace Mining Job
- Pending Synonym Rules
- LLM Suggestion Pipeline
- ValueIndexBuilder
- QueryIntentClassifier
- Feedback Review UI / endpoint
- Rule Promotion Pipeline

## Başarı Kriterleri
- Golden query sayısı: 150–300
- Table Recall: >= 0.94
- Column Recall: >= 0.90
- Invalid SQL Rate: <= %7
- Low confidence oranı düşmeli
- Manuel müdahale ile sistem iyileştirilebilir olmalı
