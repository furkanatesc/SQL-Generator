import re
from typing import Dict, Any, Set, List

from app.nlp.text_normalizer import TextNormalizer

class SchemaLexiconBuilder:
    def __init__(self, normalizer: TextNormalizer = None):
        self.normalizer = normalizer or TextNormalizer()

    def build_lexicon(self, schema: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Şemayı analiz edip otomatik sözlük oluşturur.
        Döndürdüğü yapı:
        {
          "doktor": {
            "tables": ["HST_DOKTOR"],
            "columns": ["HST_DOKTOR.doktor_id", "HST_DOKTOR.doktor_adi"],
            "source": "schema"
          }
        }
        """
        lexicon = {}
        
        tables = schema.get("tables", {})
        
        for table_name, table_meta in tables.items():
            # Tablo isminden tokenları çıkar
            table_tokens = self.normalizer.tokenize(table_name)
            for token in table_tokens:
                if token not in lexicon:
                    lexicon[token] = {"tables": set(), "columns": set(), "source": "schema"}
                lexicon[token]["tables"].add(table_name)
                
            # Kolon isimlerinden tokenları çıkar
            for col in table_meta.get("columns", []):
                col_name = col.get("name", "")
                full_col_name = f"{table_name}.{col_name}"
                col_tokens = self.normalizer.tokenize(col_name)
                
                for token in col_tokens:
                    if token not in lexicon:
                        lexicon[token] = {"tables": set(), "columns": set(), "source": "schema"}
                    lexicon[token]["columns"].add(full_col_name)
                    # Kolonun geçtiği tabloyu da işaretle
                    lexicon[token]["tables"].add(table_name)
                    
        # Set'leri listeye çevir (JSON serialize edilebilsin diye)
        for token, data in lexicon.items():
            data["tables"] = list(data["tables"])
            data["columns"] = list(data["columns"])
            
        return lexicon
