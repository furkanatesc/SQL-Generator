import os
import json
import sqlite3
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import oracledb

try:
    oracledb.init_oracle_client()
except Exception:
    pass

import copy
from thefuzz import process
from app.schema_embedding import SchemaEmbeddingIndex
import threading

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema_cache.json")
_schema_lock = threading.Lock()


def _is_truthy_config(value) -> bool:
    """Tolerant truthiness for configs-table string flags (28.x pattern)."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"} if value is not None else False


def get_db_connection_params() -> Dict[str, Any]:
    """
    SQLite settings tablosundan bağlantı parametrelerini okur.
    """
    from app.database import get_config
    db_type = get_config("target_db_type") or "sqlite" # default target is sqlite for easy local testing
    
    return {
        "type": db_type,
        "sqlite_path": get_config("target_sqlite_path") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "target_test.db"),
        "pg_host": get_config("target_pg_host") or "localhost",
        "pg_port": get_config("target_pg_port") or "5432",
        "pg_user": get_config("target_pg_user") or "postgres",
        "pg_password": get_config("target_pg_password") or "",
        "target_pg_db": get_config("target_pg_db") or "postgres",
        # Oracle bağlantı parametreleri
        "oracle_host": get_config("target_oracle_host") or "localhost",
        "oracle_port": get_config("target_oracle_port") or "1521",
        "oracle_user": get_config("target_oracle_user") or "system",
        "oracle_password": get_config("target_oracle_password") or "",
        "oracle_service": get_config("target_oracle_service") or "ORCL",
    }

class SchemaManager:
    def __init__(self):
        self.params = get_db_connection_params()

    def get_connection(self):
        if self.params["type"] == "postgres":
            conn = psycopg2.connect(
                host=self.params["pg_host"],
                port=self.params["pg_port"],
                user=self.params["pg_user"],
                password=self.params["pg_password"],
                database=self.params["target_pg_db"]
            )
            return conn
        elif self.params["type"] == "oracle":
            err_service = None
            try:
                dsn = oracledb.makedsn(
                    self.params["oracle_host"],
                    int(self.params["oracle_port"]),
                    service_name=self.params["oracle_service"]
                )
                conn = oracledb.connect(
                    user=self.params["oracle_user"],
                    password=self.params["oracle_password"],
                    dsn=dsn
                )
                return conn
            except Exception as e:
                err_service = str(e)
                
            # Fallback to SID if Service Name fails
            try:
                dsn = oracledb.makedsn(
                    self.params["oracle_host"],
                    int(self.params["oracle_port"]),
                    sid=self.params["oracle_service"]
                )
                conn = oracledb.connect(
                    user=self.params["oracle_user"],
                    password=self.params["oracle_password"],
                    dsn=dsn
                )
                return conn
            except Exception as e:
                err_sid = str(e)
                raise Exception(f"Oracle bağlantı hatası! \nService Name Denemesi: {err_service} \nSID Denemesi: {err_sid}")
        else: # sqlite
            conn = sqlite3.connect(self.params["sqlite_path"])
            conn.row_factory = sqlite3.Row
            return conn

    def get_raw_schema(self) -> Dict[str, Any]:
        """
        Veritabanından tablo, kolon ve Foreign Key ilişkilerini okuyarak ham şema topolojisini çıkartır (Filtre uygulanmaz).
        """
        if self.params["type"] == "postgres":
            return self._extract_postgres_metadata()
        elif self.params["type"] == "oracle":
            return self._extract_oracle_metadata()
        else:
            return self._extract_sqlite_metadata()

    def extract_schema_metadata(self) -> Dict[str, Any]:
        """
        Veritabanından tablo, kolon ve Foreign Key ilişkilerini okuyarak şema topolojisini çıkartır.
        """
        schema = self.get_raw_schema()
        import copy
        schema = copy.deepcopy(schema)
            
        # Filtreleri Uygula
        try:
            from app.database import get_config
            import json
            db_type = self.params["type"]
            hidden_tables_str = get_config(f"hidden_tables_{db_type}") or "[]"
            hidden_columns_str = get_config(f"hidden_columns_{db_type}") or "{}"
            hidden_tables = set(json.loads(hidden_tables_str))
            hidden_columns = json.loads(hidden_columns_str) # dict {table_name: [cols]}
            
            # Tabloları sil
            for ht in hidden_tables:
                if ht in schema["tables"]:
                    del schema["tables"][ht]
                if ht in schema["graph"]["nodes"]:
                    schema["graph"]["nodes"].remove(ht)
                    
            # Kolonları sil
            for t, cols in hidden_columns.items():
                if t in schema["tables"]:
                    hidden_cols_set = set(cols)
                    schema["tables"][t]["columns"] = [
                        c for c in schema["tables"][t]["columns"] 
                        if c["name"] not in hidden_cols_set
                    ]
                    
            # Silinmiş tablolara giden foreign key'leri (edges) temizle
            new_edges = []
            for edge in schema.get("graph", {}).get("edges", []):
                if edge["source"] not in hidden_tables and edge["target"] not in hidden_tables:
                    new_edges.append(edge)
            schema["graph"]["edges"] = new_edges
            
            for t, t_meta in schema["tables"].items():
                new_fks = []
                for fk in t_meta.get("foreign_keys", []):
                    if fk["referenced_table"] not in hidden_tables:
                        new_fks.append(fk)
                t_meta["foreign_keys"] = new_fks
                
        except Exception as e:
            print(f"Filter application failed: {e}")

        return schema

    def _current_normalized_structure(self) -> Dict[str, Any]:
        """28.7: filtered structural view for drift detection (reuses extract; no new SQL)."""
        from app.schema.schema_signature import normalize_structure
        return normalize_structure(self.extract_schema_metadata())

    def _current_schema_signature(self) -> str:
        from app.schema.schema_signature import compute_schema_signature
        return compute_schema_signature(self._current_normalized_structure())

    def get_cached_schema_signature(self) -> Optional[str]:
        """28.9: cheap read of the persisted schema_signature (NO DB extract).

        Returns None on missing/legacy/unreadable cache -> caller disables the
        result cache for that request (safe degradation)."""
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            sig = data.get("schema_signature")
            return sig if isinstance(sig, str) else None
        except Exception:
            return None

    def _extract_sqlite_metadata(self) -> Dict[str, Any]:
        schema = {"tables": {}, "graph": {"nodes": [], "edges": []}}
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Tabloları listele
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'configs' AND name NOT LIKE 'jobs'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                schema["tables"][table] = {
                    "columns": [],
                    "foreign_keys": [],
                    "constraints": []
                }
                schema["graph"]["nodes"].append(table)
                
                # Kolon bilgilerini çek
                cursor.execute(f"PRAGMA table_info({table})")
                columns_info = cursor.fetchall()
                # columns_info format: (cid, name, type, notnull, dflt_value, pk)
                for col in columns_info:
                    schema["tables"][table]["columns"].append({
                        "name": col["name"] if isinstance(col, sqlite3.Row) else col[1],
                        "type": col["type"] if isinstance(col, sqlite3.Row) else col[2],
                        "primary_key": bool(col["pk"] if isinstance(col, sqlite3.Row) else col[5]),
                        "nullable": not bool(col["notnull"] if isinstance(col, sqlite3.Row) else col[3])
                    })
                
                # Yabancı anahtar (FK) bilgilerini çek
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                fk_info = cursor.fetchall()
                # fk_info format: (id, seq, table, from, to, on_update, on_delete, match)
                for fk in fk_info:
                    ref_table = fk["table"] if isinstance(fk, sqlite3.Row) else fk[2]
                    from_col = fk["from"] if isinstance(fk, sqlite3.Row) else fk[3]
                    to_col = fk["to"] if isinstance(fk, sqlite3.Row) else fk[4]
                    
                    schema["tables"][table]["foreign_keys"].append({
                        "column": from_col,
                        "referenced_table": ref_table,
                        "referenced_column": to_col
                    })
                    
                    # Graph edges'e ekle
                    schema["graph"]["edges"].append({
                        "source": table,
                        "target": ref_table,
                        "source_col": from_col,
                        "target_col": to_col
                    })
            
            conn.close()
        except Exception as e:
            print(f"Error extracting SQLite schema: {e}")
            
        return schema

    def _extract_postgres_metadata(self) -> Dict[str, Any]:
        schema = {"tables": {}, "graph": {"nodes": [], "edges": []}}
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Tabloları çek
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_type = 'BASE TABLE'
            """)
            tables = [row["table_name"] for row in cursor.fetchall()]
            
            # Primary Key'leri bul
            cursor.execute("""
                SELECT kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY' 
                  AND tc.table_schema = 'public'
            """)
            pks = {}
            for row in cursor.fetchall():
                pks.setdefault(row["table_name"], []).append(row["column_name"])
            
            # Kolon detaylarını çek
            for table in tables:
                schema["tables"][table] = {
                    "columns": [],
                    "foreign_keys": [],
                    "constraints": []
                }
                schema["graph"]["nodes"].append(table)
                
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                """, (table,))
                
                for col in cursor.fetchall():
                    col_name = col["column_name"]
                    is_pk = col_name in pks.get(table, [])
                    schema["tables"][table]["columns"].append({
                        "name": col_name,
                        "type": col["data_type"],
                        "primary_key": is_pk,
                        "nullable": col["is_nullable"] == "YES"
                    })
                    
            # Foreign Key'leri çek
            cursor.execute("""
                SELECT
                    tc.table_name AS source_table,
                    kcu.column_name AS source_column,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY' 
                  AND tc.table_schema = 'public'
            """)
            
            for fk in cursor.fetchall():
                src_table = fk["source_table"]
                src_col = fk["source_column"]
                ref_table = fk["referenced_table"]
                ref_col = fk["referenced_column"]
                
                if src_table in schema["tables"]:
                    schema["tables"][src_table]["foreign_keys"].append({
                        "column": src_col,
                        "referenced_table": ref_table,
                        "referenced_column": ref_col
                    })
                    
                    schema["graph"]["edges"].append({
                        "source": src_table,
                        "target": ref_table,
                        "source_col": src_col,
                        "target_col": ref_col
                    })
            
            conn.close()
        except Exception as e:
            print(f"Error extracting Postgres schema: {e}")
            
        return schema

    def _extract_oracle_metadata(self) -> Dict[str, Any]:
        schema = {"tables": {}, "graph": {"nodes": [], "edges": []}}
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            owner = self.params["oracle_user"].upper()
            
            # Tabloları çek
            cursor.execute("""
                SELECT table_name 
                FROM all_tables 
                WHERE owner = :owner
                ORDER BY table_name
            """, {"owner": owner})
            tables = [row[0] for row in cursor.fetchall()]
            
            # Primary Key'leri toplu çek
            cursor.execute("""
                SELECT acc.table_name, acc.column_name
                FROM all_constraints ac
                JOIN all_cons_columns acc 
                  ON ac.constraint_name = acc.constraint_name
                  AND ac.owner = acc.owner
                WHERE ac.constraint_type = 'P'
                  AND ac.owner = :owner
            """, {"owner": owner})
            pks = {}
            for row in cursor.fetchall():
                pks.setdefault(row[0], []).append(row[1])
            
            # Tüm Constraint'leri toplu çek
            cursor.execute("""
                SELECT ac.table_name, ac.constraint_name, ac.constraint_type, ac.search_condition
                FROM all_constraints ac
                WHERE ac.owner = :owner
            """, {"owner": owner})
            constraints = {}
            for row in cursor.fetchall():
                t_name, c_name, c_type, search_cond = row
                constraints.setdefault(t_name, []).append({
                    "name": c_name,
                    "type": c_type,
                    "condition": str(search_cond) if search_cond else None
                })
                
            # Sequence'leri toplu çek
            cursor.execute("""
                SELECT sequence_name, min_value, max_value, increment_by
                FROM all_sequences
                WHERE sequence_owner = :owner
            """, {"owner": owner})
            sequences = [{"name": row[0], "min": row[1], "max": row[2], "inc": row[3]} for row in cursor.fetchall()]
            schema["sequences"] = sequences
            
            # Kolon detaylarını toplu çek
            cursor.execute("""
                SELECT table_name, column_name, data_type, nullable, data_length, data_precision, data_scale
                FROM all_tab_columns
                WHERE owner = :owner
                ORDER BY table_name, column_id
            """, {"owner": owner})
            
            all_cols = cursor.fetchall()

            for table in tables:
                schema["tables"][table] = {
                    "columns": [],
                    "foreign_keys": [],
                    "constraints": constraints.get(table, [])
                }
                schema["graph"]["nodes"].append(table)

            for col in all_cols:
                t_name = col[0]
                if t_name not in schema["tables"]:
                    continue
                    
                col_name = col[1]
                data_type = col[2]
                nullable = col[3]
                data_length = col[4]
                data_precision = col[5]
                data_scale = col[6]
                
                # Oracle veri tipini okunabilir formata çevir
                if data_type in ('NUMBER',) and data_precision is not None:
                    type_str = f"NUMBER({data_precision},{data_scale or 0})"
                elif data_type in ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR'):
                    type_str = f"{data_type}({data_length})"
                else:
                    type_str = data_type
                
                is_pk = col_name in pks.get(t_name, [])
                schema["tables"][t_name]["columns"].append({
                    "name": col_name,
                    "type": type_str,
                    "primary_key": is_pk,
                    "nullable": nullable == 'Y'
                })
            
            # Foreign Key'leri çek
            cursor.execute("""
                SELECT 
                    a.table_name AS source_table,
                    acol.column_name AS source_column,
                    b.table_name AS referenced_table,
                    bcol.column_name AS referenced_column
                FROM all_constraints a
                JOIN all_cons_columns acol 
                  ON a.constraint_name = acol.constraint_name 
                  AND a.owner = acol.owner
                JOIN all_constraints b 
                  ON a.r_constraint_name = b.constraint_name 
                  AND a.r_owner = b.owner
                JOIN all_cons_columns bcol 
                  ON b.constraint_name = bcol.constraint_name 
                  AND b.owner = bcol.owner
                  AND acol.position = bcol.position
                WHERE a.constraint_type = 'R'
                  AND a.owner = :owner
            """, {"owner": owner})
            
            for fk in cursor.fetchall():
                src_table = fk[0]
                src_col = fk[1]
                ref_table = fk[2]
                ref_col = fk[3]
                
                if src_table in schema["tables"]:
                    schema["tables"][src_table]["foreign_keys"].append({
                        "column": src_col,
                        "referenced_table": ref_table,
                        "referenced_column": ref_col
                    })
                    
                    schema["graph"]["edges"].append({
                        "source": src_table,
                        "target": ref_table,
                        "source_col": src_col,
                        "target_col": ref_col
                    })
            
            conn.close()
        except Exception as e:
            print(f"Error extracting Oracle schema: {e}")
            
        return schema


    def load_schema(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Şemayı yükler. Önce veritabanından ham şemayı (explicit) çeker (veya cache'den okur).
        Embedding indeksini kontrol eder, yoksa hesaplar.
        Ardından kullanıcı tanımlı ve implicit ilişkileri dinamik olarak giydirip döner.
        Global kilit (Thread Lock) ile önbellek izdihamını (Cache Stampede) önler.
        """
        global _schema_lock
        with _schema_lock:
            from app.database import get_config
            from app.schema_cache_fingerprint import compute_cache_fingerprint
            db_type = self.params["type"]
            # Cheap model read for the fingerprint — SchemaEmbeddingIndex()/NVIDIAEmbeddingClient() __init__ must stay side-effect-free (no I/O) since this runs on every load, including cache hits.
            current_model = SchemaEmbeddingIndex().embedding_client.model
            current_fp = compute_cache_fingerprint(
                db_type=db_type,
                hidden_tables_raw=get_config(f"hidden_tables_{db_type}"),
                hidden_columns_raw=get_config(f"hidden_columns_{db_type}"),
                embedding_model=current_model,
            )

            base_schema = None
            embeddings = None
            cached_signature = None
            old_embeddings_for_reindex = None

            if not force_refresh and os.path.exists(CACHE_PATH):
                try:
                    with open(CACHE_PATH, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        if cache_data.get("cache_fingerprint") == current_fp:
                            base_schema = cache_data["schema"]
                            embeddings = cache_data.get("embeddings")
                            cached_signature = cache_data.get("schema_signature")
                            old_embeddings_for_reindex = cache_data.get("embeddings")
                except Exception as e:
                    print(f"Failed to read schema cache: {e}")

            # 28.7: opt-in structural drift check (default OFF preserves 28.6 semantics).
            if base_schema is not None and not force_refresh \
                    and _is_truthy_config(get_config("auto_schema_drift_check")):
                try:
                    if self._current_schema_signature() != cached_signature:
                        print("[SchemaManager] Structural schema drift detected; re-extracting.")
                        base_schema = None
                        embeddings = None
                except Exception as e:
                    print(f"Schema drift check failed: {e}")

            if base_schema is None or embeddings is None or force_refresh:
                if base_schema is None:
                    base_schema = self.extract_schema_metadata()
                
                # 28.8: granular re-index — embed only new/changed tables, reuse the rest.
                print("[SchemaManager] Schema Embedding Index (granular re-index) hesaplanıyor...")
                try:
                    from app.schema_reindex import reindex_embeddings
                    schema_embedder = SchemaEmbeddingIndex()
                    _model = schema_embedder.embedding_client.model
                    from app.rag_manager import RAGManager
                    _rag = RAGManager()
                    embeddings, _reindex_report = reindex_embeddings(
                        old_embeddings=old_embeddings_for_reindex,
                        new_schema=base_schema,
                        model=_model,
                        embedder=schema_embedder,
                        rag=_rag,
                        force=force_refresh,
                    )
                    try:
                        _rag.prune_schema_ddl_points(set((base_schema or {}).get("tables", {}).keys()))
                    except Exception as e:
                        print(f"schema_ddl prune skipped: {e}")
                except Exception as e:
                    print(f"Failed to build schema embeddings (reindex): {e}")
                    embeddings = None

                try:
                    from app.schema.schema_signature import (
                        compute_schema_signature, normalize_structure)
                    schema_signature = compute_schema_signature(
                        normalize_structure(base_schema))
                    cache_payload = {
                        "cache_fingerprint": current_fp,
                        "db_type": self.params["type"],
                        "schema_signature": schema_signature,
                        "schema": base_schema,
                        "embeddings": embeddings
                    }
                    with open(CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(cache_payload, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Failed to write schema cache: {e}")
                
        # Derin kopya alıp giydirme işlemini gerçekleştirelim
        import copy
        schema = copy.deepcopy(base_schema)
        # Embedding'leri de şemaya ekleyelim ki diğer modüller kullanabilsin
        schema["embeddings"] = embeddings
        
        # Qdrant'a yükleme (Arka planda sadece yoksa yükler)
        try:
            from app.rag_manager import RAGManager
            rag_mngr = RAGManager()
            rag_mngr.index_schema_batch(schema)
        except Exception as e:
            print(f"Failed to index schema into Qdrant RAG: {e}")

        
        # 1. Ham veritabanı ilişkilerini "explicit" olarak etiketleyelim
        for edge in schema.get("graph", {}).get("edges", []):
            if "type" not in edge:
                edge["type"] = "explicit"
        for table_meta in schema.get("tables", {}).values():
            for fk in table_meta.get("foreign_keys", []):
                if "type" not in fk:
                    fk["type"] = "explicit"
                    
        # 2. Custom (manuel) kullanıcı ilişkilerini SQLite'tan yükle ve ekle
        from app.database import get_config
        custom_relations_str = get_config("custom_relations") or "[]"
        try:
            custom_relations = json.loads(custom_relations_str)
        except Exception:
            custom_relations = []
            
        for cr in custom_relations:
            src = cr.get("source")
            src_col = cr.get("source_col")
            tgt = cr.get("target")
            tgt_col = cr.get("target_col")
            
            if src in schema["tables"] and tgt in schema["tables"]:
                # Mükerrer kontrolü
                exists = any(
                    e["source"] == src and e["source_col"] == src_col and e["target"] == tgt and e["target_col"] == tgt_col
                    for e in schema["graph"]["edges"]
                )
                if not exists:
                    schema["graph"]["edges"].append({
                        "source": src,
                        "source_col": src_col,
                        "target": tgt,
                        "target_col": tgt_col,
                        "type": "custom"
                    })
                    schema["tables"][src]["foreign_keys"].append({
                        "column": src_col,
                        "referenced_table": tgt,
                        "referenced_column": tgt_col,
                        "type": "custom"
                    })
                    
        from app.schema.implicit_relationships import detect_implicit_relationships
        
        typed_relationships = detect_implicit_relationships(schema)
        implicit_relations = [
            {
                "source": rel.source_table,
                "source_col": rel.source_column,
                "target": rel.target_table,
                "target_col": rel.target_column,
                "type": rel.relationship_type.value,
                "confidence": rel.confidence,
                "reason": rel.reason,
                **rel.raw,
            }
            for rel in typed_relationships
        ]
        
        # O(1) lookup için mevcut kenarları (edges) SET içine alalım (O(N^2) sonsuz döngüyü önler)
        existing_edges_set = {
            (e["source"], e["source_col"], e["target"], e["target_col"])
            for e in schema["graph"]["edges"]
        }
        
        for ir in implicit_relations:
            src = ir["source"]
            src_col = ir["source_col"]
            tgt = ir["target"]
            tgt_col = ir["target_col"]
            
            key1 = (src, src_col, tgt, tgt_col)
            key2 = (tgt, tgt_col, src, src_col)
            
            if key1 not in existing_edges_set and key2 not in existing_edges_set:
                schema["graph"]["edges"].append(ir)
                existing_edges_set.add(key1)
                existing_edges_set.add(key2)
                schema["tables"][src]["foreign_keys"].append({
                    "column": src_col,
                    "referenced_table": tgt,
                    "referenced_column": tgt_col,
                    "type": "implicit"
                })
                
        # 4. Devre dışı bırakılmış (disabled) ilişkileri filtrele
        disabled_relations_str = get_config("disabled_relations") or "[]"
        try:
            disabled_relations = json.loads(disabled_relations_str)
        except Exception:
            disabled_relations = []
            
        if disabled_relations:
            disabled_keys = {
                (dr["source"], dr["source_col"], dr["target"], dr["target_col"])
                for dr in disabled_relations
            }
            disabled_keys.update({
                (dr["target"], dr["target_col"], dr["source"], dr["source_col"])
                for dr in disabled_relations
            })
            
            # Graph'tan sil
            schema["graph"]["edges"] = [
                e for e in schema["graph"]["edges"]
                if (e["source"], e["source_col"], e["target"], e["target_col"]) not in disabled_keys
            ]
            
            # Tables foreign key listesinden sil
            for t_name, t_meta in schema["tables"].items():
                t_meta["foreign_keys"] = [
                    fk for fk in t_meta.get("foreign_keys", [])
                    if (t_name, fk["column"], fk["referenced_table"], fk["referenced_column"]) not in disabled_keys
                ]
                
        return schema
