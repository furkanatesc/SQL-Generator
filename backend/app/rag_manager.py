import os
import time
import random
import logging
from typing import Dict, Any, List, Optional
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PointIdsList
from app.llm_client import get_nvidia_api_key
from app.schema.reindex_planner import stable_point_id

logger = logging.getLogger("rag_manager")

class NVIDIAEmbeddingClient:
    def __init__(self, api_key: str = None):
        self.base_url = "https://integrate.api.nvidia.com/v1/embeddings"
        self.model = "nvidia/llama-nemotron-embed-1b-v2"
        self.api_key = api_key

    def get_embedding(self, text: str, api_key: str = None) -> List[float]:
        """
        NVIDIA NIM API kullanarak metnin vektör gömüsünü (embedding) hesaplar.
        """
        key = api_key or self.api_key or get_nvidia_api_key()
        if not key:
            raise ValueError("Embedding hesaplamak için NVIDIA API Key bulunamadı!")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "input": [text],
            "encoding_format": "float",
            "input_type": "query"
        }

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                response = requests.post(self.base_url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    time.sleep(base_delay * (2 ** attempt) + random.uniform(0.1, 0.5))
                    continue
                else:
                    raise Exception(f"NVIDIA Embedding API Hatası {response.status_code}: {response.text}")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(base_delay * (2 ** attempt) + random.uniform(0.1, 0.5))

        raise Exception("Embedding hesaplaması gerçekleştirilemedi.")

    def get_embeddings_batch(self, texts: List[str], api_key: str = None) -> List[List[float]]:
        """
        NVIDIA NIM API kullanarak birden fazla metnin vektör gömüsünü (embedding) hesaplar.
        Toplu işlem (batch) ile API çağrısı sayısını azaltır.
        """
        if not texts:
            return []

        key = api_key or self.api_key or get_nvidia_api_key()
        if not key:
            raise ValueError("Embedding hesaplamak için NVIDIA API Key bulunamadı!")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        # Batching: API supports max 50 items per request usually, but let's assume texts is already batched appropriately
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
            "input_type": "query"
        }

        max_retries = 3
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    # API returns data array in the same order as input array
                    embeddings = [item["embedding"] for item in data["data"]]
                    return embeddings

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    time.sleep(base_delay * (2 ** attempt) + random.uniform(0.1, 0.5))
                    continue
                else:
                    raise Exception(f"NVIDIA Batch Embedding API Hatası {response.status_code}: {response.text}")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(base_delay * (2 ** attempt) + random.uniform(0.1, 0.5))

        raise Exception("Batch embedding hesaplaması gerçekleştirilemedi.")

_global_qdrant_client = None

class RAGManager:
    def __init__(self, embedding_client: NVIDIAEmbeddingClient = None):
        global _global_qdrant_client
        self.embedding_client = embedding_client or NVIDIAEmbeddingClient()
        
        if _global_qdrant_client is None:
            # Disk tabanlı Qdrant veritabanını başlat (Docker gerektirmez)
            qdrant_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qdrant_data")
            os.makedirs(qdrant_path, exist_ok=True)
            _global_qdrant_client = QdrantClient(path=qdrant_path)
            
        self.client = _global_qdrant_client
        self.vector_size = 2048 # Nemotron gömü boyutu
        
        # Koleksiyonları başlat
        self._init_collections()

    def _init_collections(self):
        """
        Qdrant üzerinde Şema (DDL), İş Kuralları ve SQL Geçmişi için koleksiyonları kurar.
        """
        collections = ["schema_ddl", "business_rules", "sql_history"]
        
        try:
            existing_collections = [c.name for c in self.client.get_collections().collections]
        except Exception:
            existing_collections = []
            
        for col in collections:
            if col not in existing_collections:
                self.client.create_collection(
                    collection_name=col,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
                )
        logger.info("[RAG] Qdrant koleksiyonları hazır.")

    def index_ddl(self, table_name: str, ddl_text: str, api_key: str = None) -> str:
        """
        Şema/DDL bilgisini Qdrant'a indeksler.
        """
        vector = self.embedding_client.get_embedding(ddl_text, api_key=api_key)
        point_id = stable_point_id(table_name)
        
        self.client.upsert(
            collection_name="schema_ddl",
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"table_name": table_name, "ddl": ddl_text}
                )
            ]
        )
        return table_name

    def index_schema_batch(self, schema: Dict[str, Any], api_key: str = None) -> int:
        """
        Tüm veritabanı şemasını (3000+ tablo) batch olarak Qdrant'a yükler.
        Eğer schema['embeddings']['tables'] içinde önceden hesaplanmış vektörler varsa doğrudan onları kullanır.
        Yoksa NVIDIA API ile hesaplayıp yükler.
        """
        tables = schema.get("tables", {})
        if not tables:
            return 0

        precomputed_embeddings = schema.get("embeddings", {}).get("tables", {})
        
        table_names = list(tables.keys())
        points = []
        
        # Eğer precomputed yoksa batch API ile hesapla
        if not precomputed_embeddings:
            logger.info("[RAG] Önceden hesaplanmış embedding bulunamadı. Yeni embedding'ler hesaplanacak...")
            from app.schema_embedding import SchemaEmbeddingIndex
            embedder = SchemaEmbeddingIndex(embedding_client=self.embedding_client)
            precomputed_embeddings = embedder.build_index(schema, api_key=api_key)
            
        for name in table_names:
            vector = precomputed_embeddings.get(name)
            if not vector:
                continue
                
            # Tablo yapısını text olarak sakla
            columns = [f"{c['name']} ({c.get('type', '')})" for c in tables[name].get("columns", [])]
            ddl_text = f"Table: {name} | Columns: {', '.join(columns)}"
            
            point_id = stable_point_id(name)
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"table_name": name, "ddl": ddl_text}
                )
            )
            
        # Qdrant'a batch yükleme
        if points:
            batch_size = 250
            for i in range(0, len(points), batch_size):
                batch_points = points[i:i+batch_size]
                self.client.upsert(
                    collection_name="schema_ddl",
                    points=batch_points
                )
            logger.info(f"[RAG] Toplam {len(points)} tablo Qdrant'a başarıyla indekslendi.")
            
        return len(points)

    def delete_schema_points(self, names) -> int:
        """schema_ddl'den verilen tablo adlarına ait point'leri deterministik id ile siler."""
        ids = [stable_point_id(n) for n in (names or [])]
        if not ids:
            return 0
        try:
            self.client.delete(collection_name="schema_ddl",
                               points_selector=PointIdsList(points=ids))
        except Exception as e:
            logger.warning(f"[RAG] delete_schema_points başarısız: {e}")
            return 0
        return len(ids)

    def _scroll_schema_ddl(self):
        points, offset = [], None
        while True:
            batch, offset = self.client.scroll(
                collection_name="schema_ddl", limit=1000,
                with_payload=True, offset=offset)
            points.extend(batch)
            if not offset:
                break
        return points

    def audit_schema_ddl_points(self, valid_table_names) -> dict:
        """Read-only: schema_ddl'deki orphan (şemada olmayan) ve stale-id point'leri raporlar."""
        valid = set(valid_table_names or [])
        try:
            points = self._scroll_schema_ddl()
        except Exception as e:
            logger.warning(f"[RAG] audit scroll başarısız: {e}")
            return {"orphaned": [], "stale_id": [], "total": 0}
        orphaned, stale = [], []
        for p in points:
            tname = (p.payload or {}).get("table_name")
            if tname is None:
                continue
            if tname not in valid:
                orphaned.append(tname)
            elif p.id != stable_point_id(tname):
                stale.append(tname)
        return {"orphaned": sorted(set(orphaned)), "stale_id": sorted(set(stale)),
                "total": len(points)}

    def prune_schema_ddl_points(self, valid_table_names) -> list:
        """schema_ddl'deki orphan + stale-id point'leri siler; silinen tablo adlarını döner."""
        valid = set(valid_table_names or [])
        try:
            points = self._scroll_schema_ddl()
        except Exception as e:
            logger.warning(f"[RAG] prune scroll başarısız: {e}")
            return []
        to_delete_ids, deleted_names = [], []
        for p in points:
            tname = (p.payload or {}).get("table_name")
            if tname is None:
                continue
            if tname not in valid or p.id != stable_point_id(tname):
                to_delete_ids.append(p.id)
                deleted_names.append(tname)
        if to_delete_ids:
            try:
                self.client.delete(collection_name="schema_ddl",
                                   points_selector=PointIdsList(points=to_delete_ids))
            except Exception as e:
                logger.warning(f"[RAG] prune delete başarısız: {e}")
                return []
        return sorted(set(deleted_names))

    def index_business_rule(self, rule_id: str, rule_text: str, sql_mapping: str, api_key: str = None) -> str:
        """
        İş kurallarını ve bunlara karşılık gelen SQL parçalarını Qdrant'a indeksler.
        """
        vector = self.embedding_client.get_embedding(rule_text, api_key=api_key)
        point_id = int(hash(rule_id) % 10**8)
        
        self.client.upsert(
            collection_name="business_rules",
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"rule_id": rule_id, "rule": rule_text, "sql_mapping": sql_mapping}
                )
            ]
        )
        return rule_id

    def index_sql_history(self, history_id: str, natural_query: str, sql: str, api_key: str = None) -> str:
        """
        Geçmiş başarılı SQL sorgularını (örnek sorgu çiftlerini) Qdrant'a indeksler.
        """
        vector = self.embedding_client.get_embedding(natural_query, api_key=api_key)
        point_id = int(hash(history_id) % 10**8)
        
        self.client.upsert(
            collection_name="sql_history",
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"history_id": history_id, "natural_query": natural_query, "sql": sql}
                )
            ]
        )
        return history_id

    def search_ddl(self, query_text: str, limit: int = 3, api_key: str = None) -> List[Dict[str, Any]]:
        """
        Sorgu metnine en benzer tabloları/DDL'leri semantik olarak arar.
        """
        vector = self.embedding_client.get_embedding(query_text, api_key=api_key)
        hits = self.client.search(
            collection_name="schema_ddl",
            query_vector=vector,
            limit=limit
        )
        return [{"payload": hit.payload, "score": hit.score} for hit in hits]

    def search_business_rules(self, query_text: str, limit: int = 3, api_key: str = None) -> List[Dict[str, Any]]:
        """
        Sorgu metnine en uygun iş kurallarını semantik olarak arar.
        """
        vector = self.embedding_client.get_embedding(query_text, api_key=api_key)
        hits = self.client.search(
            collection_name="business_rules",
            query_vector=vector,
            limit=limit
        )
        return [hit.payload for hit in hits]

    def search_sql_history(self, query_text: str, limit: int = 3, api_key: str = None) -> List[Dict[str, Any]]:
        """
        Doğal dil sorgusuna en yakın geçmiş SQL sorgularını Few-Shot learning için arar.
        """
        vector = self.embedding_client.get_embedding(query_text, api_key=api_key)
        hits = self.client.search(
            collection_name="sql_history",
            query_vector=vector,
            limit=limit
        )
        return [hit.payload for hit in hits]
