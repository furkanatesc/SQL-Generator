import logging
import numpy as np
from typing import Dict, Any, List, Tuple
from app.rag_manager import NVIDIAEmbeddingClient

logger = logging.getLogger("schema_embedding")

class SchemaEmbeddingIndex:
    def __init__(self, embedding_client: NVIDIAEmbeddingClient = None):
        self.embedding_client = embedding_client or NVIDIAEmbeddingClient()

    def _generate_table_fingerprint(self, table_name: str, table_meta: Dict[str, Any]) -> str:
        """
        Her tablo için semantik bir parmak izi (fingerprint) oluşturur.
        Bu parmak izi, tablonun içeriğini ve ilişkilerini anlamsal olarak temsil eder.
        """
        # Kolon isimleri ve veri tiplerini birleştir (bağlamı güçlendirmek için)
        columns = []
        for col in table_meta.get("columns", []):
            col_name = col.get("name", "")
            col_type = col.get("type") or col.get("data_type") or ""
            if col_type:
                columns.append(f"{col_name} ({col_type})")
            else:
                columns.append(col_name)
                
        # Foreign key referanslarını ekleyerek anlamsal bağı güçlendir
        fks = []
        for fk in table_meta.get("foreign_keys", []):
            fks.append(f"references {fk.get('referenced_table')}")
            
        fingerprint = f"Table: {table_name} | Columns: {', '.join(columns)}"
        if fks:
            fingerprint += f" | Relations: {', '.join(fks)}"
            
        return fingerprint

    def build_index(self, schema: Dict[str, Any], api_key: str = None) -> Dict[str, List[float]]:
        """
        Şemadaki tüm tabloların semantik parmak izlerini oluşturur ve batch API 
        kullanarak embedding vektörlerini hesaplar.
        """
        tables = schema.get("tables", {})
        if not tables:
            return {}

        table_names = list(tables.keys())
        fingerprints = []
        
        for name in table_names:
            fingerprint = self._generate_table_fingerprint(name, tables[name])
            fingerprints.append(fingerprint)
            
        logger.info(f"[SchemaEmbedding] {len(table_names)} tablo için semantik parmak izleri oluşturuldu. Embedding hesaplanıyor...")
        
        try:
            # NVIDIA API'ye batch istek gönder (limitlere dikkat et, gerekirse parçala)
            batch_size = 50
            all_embeddings = []
            
            for i in range(0, len(fingerprints), batch_size):
                batch_fingerprints = fingerprints[i:i+batch_size]
                batch_embeddings = self.embedding_client.get_embeddings_batch(batch_fingerprints, api_key=api_key)
                all_embeddings.extend(batch_embeddings)
                
            # Tablo ismi ile embedding vektörünü eşleştir
            table_embeddings = {
                name: emb for name, emb in zip(table_names, all_embeddings)
            }
            logger.info("[SchemaEmbedding] Tüm tabloların embedding hesaplamaları tamamlandı.")
            return table_embeddings
            
        except Exception as e:
            logger.error(f"[SchemaEmbedding] Embedding indeksleme başarısız: {str(e)}")
            return {}

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """
        İki vektör arasındaki kosinüs benzerliğini hesaplar (numpy kullanarak).
        """
        a = np.array(vec_a)
        b = np.array(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(np.dot(a, b) / (norm_a * norm_b))

    def find_relevant_tables(
        self, 
        query: str, 
        table_embeddings: Dict[str, List[float]], 
        api_key: str = None, 
        top_k: int = 5, 
        threshold: float = 0.3
    ) -> List[Tuple[str, float]]:
        """
        Sorgu metnine en uygun tabloları cosine similarity ile bulur.
        Dönen değer: [(table_name, similarity_score), ...]
        """
        if not query or not table_embeddings:
            return []
            
        try:
            # Sorgunun embedding vektörünü hesapla (tek API çağrısı)
            query_vector = self.embedding_client.get_embedding(query, api_key=api_key)
        except Exception as e:
            logger.error(f"[SchemaEmbedding] Sorgu embedding'i hesaplanamadı: {str(e)}")
            return []
            
        # Benzerlikleri hesapla
        similarities = []
        for table_name, table_vector in table_embeddings.items():
            sim = self.cosine_similarity(query_vector, table_vector)
            if sim >= threshold:
                similarities.append((table_name, sim))
                
        # Skora göre azalan şekilde sırala ve top_k tanesini al
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
