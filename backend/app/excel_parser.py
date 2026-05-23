import openpyxl
import os
from typing import Dict, Any, List, Optional

def parse_excel_request(file_path: str) -> Dict[str, Any]:
    """
    Excel talep dosyasını ayrıştırıp yapılandırılmış Abstract Query Representation (AQR) nesnesi üretir.
    Dosyada 'Sorgu Talebi' veya 'Query Request' isimli özel bir sayfa aranır.
    Bulunamazsa ilk sayfadaki doğal dil sorusu ve genel veriler okunur.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Excel file not found at: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=True)
    
    # Özel sayfaları ara
    target_sheet = None
    for name in ["Sorgu Talebi", "Query Request", "Request", "Talep"]:
        if name in wb.sheetnames:
            target_sheet = wb[name]
            break
            
    # Varsayılan AQR şablonu
    aqr = {
        "entities": [],
        "fields": [],
        "filters": [],
        "aggregations": [],
        "sorts": [],
        "natural_query": "",
        "business_rules": []
    }
    
    if target_sheet:
        # Yapılandırılmış sayfayı ayrıştır
        # A sütununda anahtar kelimeler arayalım ve altındaki satırları okuyalım
        current_section = None
        
        for row in target_sheet.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
                
            cell_val = str(row[0]).strip().lower()
            
            # Bölüm tespiti
            if "tablolar" in cell_val or "entities" in cell_val or "varlıklar" in cell_val:
                current_section = "entities"
                continue
            elif "sütunlar" in cell_val or "fields" in cell_val or "alanlar" in cell_val:
                current_section = "fields"
                continue
            elif "filtreler" in cell_val or "filters" in cell_val or "koşullar" in cell_val:
                current_section = "filters"
                continue
            elif "hesaplamalar" in cell_val or "aggregations" in cell_val or "metrikler" in cell_val:
                current_section = "aggregations"
                continue
            elif "sıralama" in cell_val or "sorting" in cell_val:
                current_section = "sorts"
                continue
            elif "doğal dil" in cell_val or "natural query" in cell_val or "talep" in cell_val:
                current_section = "natural_query"
                # Aynı satırda talep değeri varsa al
                if len(row) > 1 and row[1]:
                    aqr["natural_query"] = str(row[1]).strip()
                continue
            elif "iş kuralları" in cell_val or "business rules" in cell_val:
                current_section = "business_rules"
                continue
                
            # Değerleri bölümlere göre yerleştir
            if current_section == "entities":
                aqr["entities"].append(str(row[0]).strip())
            elif current_section == "fields":
                aqr["fields"].append(str(row[0]).strip())
            elif current_section == "filters":
                # Filtre formatı: "kolon | operatör | değer" veya tek satırda filtre tanımı
                val = str(row[0]).strip()
                if "|" in val:
                    parts = [p.strip() for p in val.split("|")]
                    if len(parts) >= 3:
                        aqr["filters"].append({"field": parts[0], "operator": parts[1], "value": parts[2]})
                    else:
                        aqr["filters"].append({"raw": val})
                else:
                    aqr["filters"].append({"raw": val})
            elif current_section == "aggregations":
                val = str(row[0]).strip()
                if "|" in val:
                    parts = [p.strip() for p in val.split("|")]
                    if len(parts) >= 2:
                        aqr["aggregations"].append({"field": parts[0], "function": parts[1], "alias": parts[2] if len(parts) > 2 else None})
                    else:
                        aqr["aggregations"].append({"raw": val})
                else:
                    aqr["aggregations"].append({"raw": val})
            elif current_section == "sorts":
                val = str(row[0]).strip()
                if "|" in val:
                    parts = [p.strip() for p in val.split("|")]
                    aqr["sorts"].append({"field": parts[0], "direction": parts[1] if len(parts) > 1 else "ASC"})
                else:
                    aqr["sorts"].append({"field": val, "direction": "ASC"})
            elif current_section == "natural_query" and not aqr["natural_query"]:
                aqr["natural_query"] = str(row[0]).strip()
            elif current_section == "business_rules":
                aqr["business_rules"].append(str(row[0]).strip())
    else:
        # Özel şablon sayfası yoksa, ilk sayfadaki genel bilgileri akıllıca okumaya çalış
        first_sheet = wb.worksheets[0]
        
        # A1 hücresi genellikle doğal dil sorgusu/sorusudur
        a1_val = first_sheet["A1"].value
        if a1_val:
            aqr["natural_query"] = str(a1_val).strip()
            
        # Diğer satırlardaki iş kurallarını topla (varsa)
        for row_idx in range(2, min(20, first_sheet.max_row + 1)):
            cell_val = first_sheet.cell(row=row_idx, column=1).value
            if cell_val:
                rule_str = str(cell_val).strip()
                # Çok uzun değilse iş kuralı olarak ekle
                if len(rule_str) > 3 and not rule_str.lower().startswith("doğal dil"):
                    aqr["business_rules"].append(rule_str)
                    
    # Temizlik ve boşluk kontrolleri
    # En azından bir doğal sorgu olmalı
    if not aqr["natural_query"]:
        # Eğer hiç yoksa ilk sayfadan okuyabildiğimiz ilk hücreyi koyalım
        for row in wb.worksheets[0].iter_rows(values_only=True):
            for cell in row:
                if cell:
                    aqr["natural_query"] = str(cell).strip()
                    break
            if aqr["natural_query"]:
                break
                
    wb.close()
    return aqr
