// SQL'i üst-düzey clause'lara ayıran deterministik, salt-okunur ayrıştırıcı.
// Backend yalnız ham SQL döndürdüğü (doğal-dil açıklama reddedilir) için açıklama
// tamamen client-side üretilir: LLM yok, ağ yok, tam AST yok — yalnız üst-düzey
// (paren derinliği 0, tırnak dışı) clause segmentasyonu. Alt-sorgular ve string
// literal içindeki anahtar kelimeler BÖLMEZ; iç yapı body içinde ham kalır.

export interface ExplainClause {
  /** Kanonik anahtar kelime, ör. "SELECT", "GROUP BY", "LEFT JOIN" */
  keyword: string;
  /** İnsan-okur Türkçe etiket */
  label: string;
  /** Anahtar kelimeden sonraki clause metni (trim'li) */
  body: string;
}

// Çoklu-kelime anahtarlar tek-kelime öneklerinden ÖNCE denenmeli (ör. "GROUP BY"
// "GROUP"'tan; "LEFT JOIN" "JOIN"'den; "UNION ALL" "UNION"'dan önce). Sıra önemli.
const CLAUSE_DEFS: ReadonlyArray<{ words: string[]; label: string }> = [
  { words: ['SELECT'], label: 'Seçilen sütunlar' },
  { words: ['FROM'], label: 'Kaynak tablo(lar)' },
  { words: ['LEFT', 'JOIN'], label: 'Birleştirme (LEFT JOIN)' },
  { words: ['RIGHT', 'JOIN'], label: 'Birleştirme (RIGHT JOIN)' },
  { words: ['INNER', 'JOIN'], label: 'Birleştirme (INNER JOIN)' },
  { words: ['FULL', 'JOIN'], label: 'Birleştirme (FULL JOIN)' },
  { words: ['CROSS', 'JOIN'], label: 'Birleştirme (CROSS JOIN)' },
  { words: ['JOIN'], label: 'Birleştirme (JOIN)' },
  { words: ['WHERE'], label: 'Filtre koşulu (WHERE)' },
  { words: ['GROUP', 'BY'], label: 'Gruplama (GROUP BY)' },
  { words: ['HAVING'], label: 'Grup filtresi (HAVING)' },
  { words: ['ORDER', 'BY'], label: 'Sıralama (ORDER BY)' },
  { words: ['LIMIT'], label: 'Satır limiti (LIMIT)' },
  { words: ['OFFSET'], label: 'Atlama (OFFSET)' },
  { words: ['UNION', 'ALL'], label: 'Birleşim (UNION ALL)' },
  { words: ['UNION'], label: 'Birleşim (UNION)' },
  { words: ['INTERSECT'], label: 'Kesişim (INTERSECT)' },
  { words: ['EXCEPT'], label: 'Fark (EXCEPT)' },
];

const isWordChar = (ch: string): boolean => /[A-Za-z0-9_]/.test(ch);

// pos'ta (üst-düzey, tırnak dışı olduğu bilinen bir konumda) bir clause tanımıyla
// eşleşme var mı? Kelimeler arası boşluk (herhangi bir whitespace) serbest; her
// kelime word-boundary'de olmalı. Eşleşirse anahtarın bittiği index'i döner, yoksa -1.
const matchClauseAt = (
  upper: string,
  pos: number,
  words: string[],
): number => {
  let i = pos;
  for (let w = 0; w < words.length; w++) {
    const word = words[w];
    if (upper.startsWith(word, i)) {
      const after = i + word.length;
      // kelimeden sonra word-char gelirse (ör. "SELECTED") eşleşme geçersiz
      if (after < upper.length && isWordChar(upper[after])) return -1;
      i = after;
    } else {
      return -1;
    }
    // sonraki kelime için whitespace tüket (son kelime değilse en az bir boşluk gerek)
    if (w < words.length - 1) {
      let j = i;
      while (j < upper.length && /\s/.test(upper[j])) j++;
      if (j === i) return -1; // kelimeler bitişik olamaz
      i = j;
    }
  }
  return i;
};

export function explainSql(sql: string | undefined | null): ExplainClause[] {
  if (!sql || !sql.trim()) return [];

  const upper = sql.toUpperCase();
  const n = sql.length;

  // Üst-düzey clause sınırlarını topla. start = anahtarın kaynak metindeki başlangıcı,
  // bodyStart = anahtarın bitişi (body burada başlar).
  const boundaries: Array<{ keyword: string; label: string; start: number; bodyStart: number }> = [];

  let depth = 0;
  let quote: string | null = null; // "'" veya '"' içindeysek
  let atWordStart = true; // önceki karakter word-char değil mi (kelime sınırı)

  for (let i = 0; i < n; i++) {
    const ch = sql[i];

    if (quote) {
      // Tırnak içindeyiz; kapanışı ara (basit; ardışık tırnak escape'i sadeleştirilir)
      if (ch === quote) quote = null;
      atWordStart = false;
      continue;
    }

    if (ch === "'" || ch === '"') {
      quote = ch;
      atWordStart = false;
      continue;
    }

    if (ch === '(') {
      depth++;
      atWordStart = true;
      continue;
    }
    if (ch === ')') {
      if (depth > 0) depth--;
      atWordStart = false;
      continue;
    }

    if (depth === 0 && atWordStart) {
      // Bu konumda bir clause anahtarı başlıyor mu?
      let matchedEnd = -1;
      for (const def of CLAUSE_DEFS) {
        const end = matchClauseAt(upper, i, def.words);
        if (end !== -1) {
          boundaries.push({
            keyword: def.words.join(' '),
            label: def.label,
            start: i,
            bodyStart: end,
          });
          matchedEnd = end;
          break;
        }
      }
      if (matchedEnd !== -1) {
        // Eşleşen anahtarın içini yeniden taramayı önle (ör. "LEFT JOIN" içindeki
        // "JOIN"'i tekrar yakalamasın). i'yi anahtarın sonuna atlat.
        i = matchedEnd - 1;
        atWordStart = false;
        continue;
      }
    }

    atWordStart = !isWordChar(ch);
  }

  if (boundaries.length === 0) return [];

  // Sınır aralıklarından body'leri kes: body = mevcut anahtarın bitişinden bir
  // sonraki anahtarın başlangıcına kadar (yoksa metin sonu).
  const clauses: ExplainClause[] = [];
  for (let b = 0; b < boundaries.length; b++) {
    const cur = boundaries[b];
    const next = boundaries[b + 1];
    const bodyEnd = next ? next.start : n;
    const body = sql.slice(cur.bodyStart, bodyEnd).trim();
    clauses.push({ keyword: cur.keyword, label: cur.label, body });
  }

  return clauses;
}
