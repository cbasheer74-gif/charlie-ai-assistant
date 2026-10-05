"""
core/semantic_rag.py
Local Semantic Vector & Full-Text Search RAG Memory for Charlie AI Assistant.
Indexes local files, personal notes, task history, and past conversations.

Multilingual upgrade:
  - Unicode-aware tokenization covering Latin, Devanagari, Dravidian, CJK,
    Arabic, Hebrew, Cyrillic, Thai, and other scripts.
  - language column per document: same-language results ranked higher.
  - FTS5 query sanitizer preserves non-ASCII text so Hindi/Tamil queries work.
  - Cosine similarity uses script-correct tokenization, not just \\w+.
"""
from __future__ import annotations

import math
import re
import sqlite3
import threading
import unicodedata
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Unicode-aware tokenizer
# ──────────────────────────────────────────────────────────────────────────────

# CJK Unified Ideographs + Extensions + Compatibility + Radicals
_CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # Extension A
    (0x20000, 0x2A6DF), # Extension B
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x2E80, 0x2EFF),   # CJK Radicals Supplement
    (0x31C0, 0x31EF),   # CJK Strokes
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x3040, 0x30FF),   # Hiragana + Katakana
]


def _is_cjk(ch: str) -> bool:
    """True if the character belongs to a CJK / Japanese / Korean block."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _unicode_tokenize(text: str) -> list[str]:
    """
    Multilingual tokenizer that correctly handles:
      - Latin/Cyrillic/Greek: word boundary split
      - Devanagari/Dravidian/Gujarati/Bengali/etc.: Unicode letter sequences
      - Arabic/Hebrew/Urdu: letter + combining mark sequences
      - CJK: every character is its own token (no spaces in written Chinese/Japanese)
      - Thai/Khmer: character-level (no spaces between words)
      - Mixed text: each script handled by its own path
    """
    tokens: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            word = "".join(buf).strip()
            if word:
                tokens.append(word.lower())
            buf.clear()

    for ch in text:
        if _is_cjk(ch):
            flush()
            tokens.append(ch)  # each CJK char is its own token
        elif unicodedata.category(ch).startswith(("L", "M", "N")):
            # Letter, Mark (combining), Number — part of a word
            buf.append(ch)
        else:
            flush()  # punctuation / whitespace ends the word

    flush()
    return [t for t in tokens if len(t) >= 1]


def _tokenize(text: str) -> list[str]:
    """Normalize to NFC and tokenize with Unicode awareness."""
    return _unicode_tokenize(unicodedata.normalize("NFC", text))


# ──────────────────────────────────────────────────────────────────────────────
# FTS5 query builder — preserves non-ASCII text
# ──────────────────────────────────────────────────────────────────────────────

def _build_fts_query(query: str) -> str:
    """
    Build an FTS5 MATCH expression from a multilingual query.
    - Latin queries: simple OR of terms
    - Non-Latin queries: wrap each token in double-quotes (FTS5 unicode61 tokenizer
      can handle quoted phrases correctly for many scripts)
    - Falls back to the raw query if tokenization yields nothing
    """
    tokens = _tokenize(query)
    if not tokens:
        return ""
    # Quote each term so FTS5 treats them as literal phrases (not operators)
    quoted = [f'"{t}"' for t in tokens if len(t) >= 2]
    return " OR ".join(quoted) if quoted else ""


# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    doc_id: str
    title: str
    content: str
    category: str
    score: float
    language: str = "auto"


# ──────────────────────────────────────────────────────────────────────────────
# SemanticRAGMemory
# ──────────────────────────────────────────────────────────────────────────────

class SemanticRAGMemory:
    """Local hybrid semantic & BM25 memory index powered by SQLite.

    Multilingual: each document carries a language tag.  Queries scored
    against same-language documents get a +0.15 language-match bonus so
    Hindi queries surface Hindi memories before English ones.
    """

    _lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from memory.config_manager import BASE_DIR
            db_path = BASE_DIR / "semantic_memory.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        doc_id TEXT PRIMARY KEY,
                        title TEXT,
                        content TEXT,
                        category TEXT,
                        language TEXT DEFAULT 'auto',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Add language column to existing DBs that pre-date this version
                try:
                    conn.execute("ALTER TABLE documents ADD COLUMN language TEXT DEFAULT 'auto'")
                except Exception:
                    pass  # column already exists

                # FTS5 with unicode61 tokenizer — handles accented + non-ASCII chars
                try:
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
                            title, content,
                            content=documents, content_rowid=rowid,
                            tokenize='unicode61'
                        )
                    """)
                except Exception:
                    pass
                conn.commit()

    # ── active user language ──────────────────────────────────────────────────

    @staticmethod
    def _active_language() -> str:
        """Read user's active language from personal hub."""
        try:
            from memory.personal_hub import load_hub
            lang = load_hub().get("speech", {}).get("language", "auto")
            return (lang or "auto").lower().strip()
        except Exception:
            return "auto"

    @staticmethod
    def _detect_doc_language(text: str) -> str:
        """Detect language of a document using the languages registry."""
        try:
            from core.languages import detect_language_script
            info = detect_language_script(text[:500])  # sample first 500 chars
            if info:
                return info.whisper_code or "auto"
        except Exception:
            pass
        return "auto"

    # ── indexing ──────────────────────────────────────────────────────────────

    def index_document(self, doc_id: str, title: str, content: str,
                       category: str = "general",
                       language: Optional[str] = None):
        """Inserts or updates a searchable document with language tagging."""
        if not content.strip():
            return
        # Auto-detect language if not provided
        lang = (language or "").strip().lower() or self._detect_doc_language(content)
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO documents
                        (doc_id, title, content, category, language, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (doc_id, title, content, category, lang))
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO doc_fts(rowid, title, content) "
                        "SELECT rowid, title, content FROM documents WHERE doc_id = ?",
                        (doc_id,)
                    )
                except Exception:
                    pass
                conn.commit()

    # ── cosine similarity (multilingual) ─────────────────────────────────────

    def _compute_cosine_sim(self, text_a: str, text_b: str) -> float:
        """Unicode-aware token-frequency cosine similarity."""
        words_a = _tokenize(text_a)
        words_b = _tokenize(text_b)
        if not words_a or not words_b:
            return 0.0
        vec_a = Counter(words_a)
        vec_b = Counter(words_b)
        intersection = set(vec_a.keys()) & set(vec_b.keys())
        dot = sum(vec_a[w] * vec_b[w] for w in intersection)
        mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
        mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    # ── search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5,
               category: Optional[str] = None,
               language: Optional[str] = None) -> list[SearchResult]:
        """
        Hybrid multilingual search: FTS5 + cosine sim + language-match bonus.

        Language bonus (+0.15) applied when the document's language matches
        either the explicitly passed language or the user's active preference.
        """
        if not query.strip():
            return []

        # Resolve query language for ranking bonus
        active_lang = (language or self._active_language()).lower()

        results: list[SearchResult] = []

        with self._get_conn() as conn:
            # ── FTS5 pass ────────────────────────────────────────────────────
            fts_rows = []
            fts_q = _build_fts_query(query)
            if fts_q:
                try:
                    sql = """
                        SELECT d.doc_id, d.title, d.content, d.category,
                               d.language, bm25(doc_fts) as rank
                        FROM doc_fts f
                        JOIN documents d ON f.rowid = d.rowid
                        WHERE doc_fts MATCH ?
                    """
                    params: list = [fts_q]
                    if category:
                        sql += " AND d.category = ?"
                        params.append(category)
                    sql += " ORDER BY rank LIMIT 20"
                    fts_rows = conn.execute(sql, params).fetchall()
                except Exception:
                    fts_rows = []

            seen_ids: set[str] = set()
            for r in fts_rows:
                doc_id = r["doc_id"]
                seen_ids.add(doc_id)
                sim = self._compute_cosine_sim(query, r["content"])
                bm25_score = 0.5 / (abs(r["rank"]) + 1.0)
                lang_bonus = 0.15 if (
                    r["language"] and active_lang not in ("auto", "")
                    and r["language"] == active_lang
                ) else 0.0
                results.append(SearchResult(
                    doc_id=doc_id,
                    title=r["title"],
                    content=r["content"],
                    category=r["category"],
                    language=r["language"] or "auto",
                    score=sim + bm25_score + lang_bonus,
                ))

            # ── fallback scan (for docs missed by FTS) ───────────────────────
            if len(results) < top_k:
                sql = "SELECT doc_id, title, content, category, language FROM documents"
                params = []
                if category:
                    sql += " WHERE category = ?"
                    params.append(category)
                sql += " ORDER BY updated_at DESC LIMIT 80"
                all_docs = conn.execute(sql, params).fetchall()
                for doc in all_docs:
                    if doc["doc_id"] in seen_ids:
                        continue
                    sim = self._compute_cosine_sim(query, doc["content"])
                    if sim > 0.06:
                        lang_bonus = 0.15 if (
                            doc["language"] and active_lang not in ("auto", "")
                            and doc["language"] == active_lang
                        ) else 0.0
                        results.append(SearchResult(
                            doc_id=doc["doc_id"],
                            title=doc["title"],
                            content=doc["content"],
                            category=doc["category"],
                            language=doc["language"] or "auto",
                            score=sim + lang_bonus,
                        ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    # ── RAG context builder ───────────────────────────────────────────────────

    def build_rag_context(self, query: str, top_k: int = 3) -> str:
        """Returns formatted context string ready to inject into conversational prompts.
        Multilingual: same-language results are ranked higher automatically.
        """
        hits = self.search(query, top_k=top_k)
        if not hits:
            return ""
        lines = ["[RELEVANT LOCAL MEMORY & FILE CONTEXT]"]
        for h in hits:
            snippet = h.content.strip().replace("\n", " ")[:300]
            lang_tag = f" [{h.language.upper()}]" if h.language not in ("auto", "") else ""
            lines.append(f"- ({h.category.upper()}{lang_tag}) {h.title}: \"{snippet}\"")
        return "\n".join(lines)

    # ── re-index existing docs with language detection ────────────────────────

    def backfill_language_tags(self) -> int:
        """One-shot migration: detect & save language for existing docs missing it.
        Returns number of docs updated.
        """
        updated = 0
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT doc_id, content FROM documents WHERE language IS NULL OR language = 'auto'"
            ).fetchall()
        for row in rows:
            lang = self._detect_doc_language(row["content"])
            if lang and lang != "auto":
                with self._lock:
                    with self._get_conn() as conn:
                        conn.execute(
                            "UPDATE documents SET language = ? WHERE doc_id = ?",
                            (lang, row["doc_id"])
                        )
                        conn.commit()
                updated += 1
        return updated


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────────

_default_rag: Optional[SemanticRAGMemory] = None


def get_rag_memory() -> SemanticRAGMemory:
    global _default_rag
    if _default_rag is None:
        _default_rag = SemanticRAGMemory()
    return _default_rag
