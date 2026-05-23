import re
from typing import Dict, Any, Set, List

class SchemaLexiconBuilder:
    def __init__(self):
        # Türkçe karakter dönüşümleri
        self.tr_map = {
            'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g', 
            'ü': 'u', 'Ü': 'u', 'ş': 's', 'Ş': 's', 
            'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c'
        }
        
    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
            
        # Türkçe karakterleri dönüştür
        for tr, en in self.tr_map.items():
            text = text.replace(tr, en)
            
        return text.lower()

    def tokenize(self, text: str) -> Set[str]:
        if not text:
            return set()
            
        text = self.normalize_text(text)
        
        # camelCase ve PascalCase'i ayır (örn: doktorAdi -> doktor adi)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # Underscore ve alfanümerik olmayanları boşluk yap
        normalized = re.sub(r'[^a-z0-9]+', ' ', text)
        
        tokens = set()
        for t in normalized.split():
            t = t.strip()
            # Çok kısa (1 harfli) tokenları yoksay
            if len(t) >= 2:
                tokens.add(t)
                
        return tokens

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
            table_tokens = self.tokenize(table_name)
            for token in table_tokens:
                if token not in lexicon:
                    lexicon[token] = {"tables": set(), "columns": set(), "source": "schema"}
                lexicon[token]["tables"].add(table_name)
                
            # Kolon isimlerinden tokenları çıkar
            for col in table_meta.get("columns", []):
                col_name = col.get("name", "")
                full_col_name = f"{table_name}.{col_name}"
                col_tokens = self.tokenize(col_name)
                
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
