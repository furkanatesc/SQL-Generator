import re
from typing import Set

class TextNormalizer:
    """
    Sistemin tek (Single Source of Truth) metin normalizasyon ve tokenizasyon sınıfı.
    Tüm modüller (Lexicon, Pruner, Synonym) metin işleme için bu sınıfı kullanmalıdır.
    """
    def __init__(self):
        self.tr_map = {
            'ı': 'i', 'İ': 'i', 'ğ': 'g', 'Ğ': 'g', 
            'ü': 'u', 'Ü': 'u', 'ş': 's', 'Ş': 's', 
            'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c'
        }
        
        self.GENERIC_TOKENS = {
            "id", "no", "ad", "adi", "kod", "kodu",
            "tarih", "durum", "tip", "tur",
            "aktif", "pasif", "kayit", "islem", "aciklama"
        }

    def is_generic(self, token: str) -> bool:
        return token in self.GENERIC_TOKENS

    def normalize(self, text: str) -> str:
        """
        Metni Türkçe karakterlerden arındırıp lowercase yapar.
        """
        if not text:
            return ""
            
        for tr, en in self.tr_map.items():
            text = text.replace(tr, en)
            
        return text.lower()

    def tokenize(self, text: str) -> Set[str]:
        """
        Metni tokenlarına ayırır.
        """
        if not text:
            return set()
            
        # 1. camelCase ve PascalCase'i ayır (Lowercase'dan ÖNCE yapılmalı)
        text = re.sub(r'([a-zçğıöşü])([A-ZÇĞİÖŞÜ])', r'\1 \2', text)
        
        # 2. Türkçe karakter düzeltme ve lowercase
        text = self.normalize(text)
        
        # 3. Underscore ve alfanümerik olmayanları boşluk yap
        normalized = re.sub(r'[^a-z0-9]+', ' ', text)
        
        tokens = set()
        for t in normalized.split():
            t = t.strip()
            if len(t) >= 2:
                tokens.add(t)
                
        return tokens
