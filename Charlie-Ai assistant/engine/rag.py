"""engine/rag.py — Local offline RAG & document search engine.

Features:
- Multi-format ingestion: TXT, MD, PDF, DOCX, Code, CSV, JSON
- Clean chunking with overlap
- SQLite persistent storage + FTS5 full-text BM25 index
- Zero-dependency local dense embeddings (engine.semantic)
- Hybrid retrieval (BM25 + Dense Cosine Similarity) with rank fusion
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.semantic import cosine_similarity, local_dense_embedding


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_DEFAULT_DB = _app_dir() / "memory" / "rag_store.sqlite3"

_TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".json", ".csv", ".tsv", ".yaml", ".yml", ".toml",
    ".ini", ".xml", ".sql", ".sh", ".bat", ".ps1", ".c", ".cpp", ".h",
    ".cs", ".java", ".go", ".rs", ".php", ".rb", ".swift", ".kt",
}


def _extract_text_from_file(path: Path) -> str:
    """Extract raw text from supported document types."""
    ext = path.suffix.lower()

    if ext in _TEXT_EXTS:
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return ""

    if ext == ".pdf":
        # Try pdfminer
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            return pdf_extract(str(path)) or ""
        except Exception:
            pass
        # Try pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            pass
        # Try pypdf / pypdf2
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            pass
        return ""

    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception:
            return ""

    return ""


def _chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
    """Break text into semantically cohesive overlapping chunks."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Split by double newline (paragraphs) first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            # Paragraph itself exceeds chunk_size, split by sentences or slices
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if current_len + len(s) + 1 > chunk_size:
                    if current:
                        chunks.append("\n".join(current))
                    current = [s]
                    current_len = len(s)
                else:
                    current.append(s)
                    current_len += len(s) + 1
        else:
            if current_len + len(para) + 2 > chunk_size:
                if current:
                    chunks.append("\n\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    # Apply overlap smoothing if chunks are disconnected
    if overlap > 0 and len(chunks) > 1:
        smoothed: List[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:].strip()
            if prev_tail and not chunks[i].startswith(prev_tail):
                smoothed.append(f"...{prev_tail}\n{chunks[i]}")
            else:
                smoothed.append(chunks[i])
        chunks = smoothed

    return chunks


class LocalRAG:
    """Thread-safe, local vector + BM25 document search engine."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    doc_hash TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
                );
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    content='chunks',
                    content_rowid='id'
                );
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.id, old.content);
                END;
            """)
            conn.commit()

    def index_file(self, file_path: str | Path) -> Dict[str, Any]:
        """Index or update a single file. Skips unchanged files by hash."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return {"status": "error", "error": f"File not found: {path}"}

        stat = path.stat()
        mtime = stat.st_mtime
        size = stat.st_size

        text = _extract_text_from_file(path)
        if not text.strip():
            return {"status": "skipped", "reason": "empty or unreadable format", "path": str(path)}

        doc_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

        with self._lock, self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, doc_hash FROM documents WHERE path = ?", (str(path),))
            row = cur.fetchone()

            if row and row["doc_hash"] == doc_hash:
                return {
                    "status": "up_to_date",
                    "path": str(path),
                    "filename": path.name,
                    "doc_id": row["id"],
                }

            # Delete old record if re-indexing
            if row:
                cur.execute("DELETE FROM documents WHERE id = ?", (row["id"],))

            chunks = _chunk_text(text)
            now_iso = datetime.now(timezone.utc).isoformat()

            cur.execute("""
                INSERT INTO documents (path, filename, extension, doc_hash, mtime, size_bytes, chunk_count, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(path), path.name, path.suffix.lower(), doc_hash, mtime, size, len(chunks), now_iso))

            doc_id = cur.lastrowid

            for idx, chunk_str in enumerate(chunks):
                emb = local_dense_embedding(chunk_str)
                cur.execute("""
                    INSERT INTO chunks (doc_id, chunk_index, content, embedding)
                    VALUES (?, ?, ?, ?)
                """, (doc_id, idx, chunk_str, json.dumps(emb)))

            conn.commit()

        return {
            "status": "indexed",
            "path": str(path),
            "filename": path.name,
            "doc_id": doc_id,
            "chunks": len(chunks),
        }

    def index_directory(
        self,
        folder_path: str | Path,
        recursive: bool = True,
        extensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Index all supported documents in a directory."""
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            return {"status": "error", "error": f"Directory not found: {folder}"}

        target_exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else (_TEXT_EXTS | {".pdf", ".docx"})

        indexed = 0
        skipped = 0
        errors = 0
        total_chunks = 0

        pattern = "**/*" if recursive else "*"
        for p in folder.glob(pattern):
            if p.is_file() and p.suffix.lower() in target_exts:
                # Skip hidden/venv
                parts = set(p.parts)
                if any(x.startswith(".") or x in ("node_modules", "__pycache__", "venv", ".venv") for x in parts):
                    continue

                res = self.index_file(p)
                if res.get("status") == "indexed":
                    indexed += 1
                    total_chunks += res.get("chunks", 0)
                elif res.get("status") in ("up_to_date", "skipped"):
                    skipped += 1
                else:
                    errors += 1

        return {
            "status": "completed",
            "folder": str(folder),
            "indexed_files": indexed,
            "skipped_files": skipped,
            "failed_files": errors,
            "total_new_chunks": total_chunks,
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_ext: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining SQLite FTS5 (BM25) and Dense Cosine Similarity."""
        query = str(query or "").strip()
        if not query:
            return []

        query_vec = local_dense_embedding(query)
        clean_fts_query = re.sub(r"[^\w\s]", " ", query).strip()

        with self._lock, self._connection() as conn:
            cur = conn.cursor()

            # 1. FTS5 BM25 search
            fts_scores: Dict[int, float] = {}
            if clean_fts_query:
                # Format FTS tokens with OR for high recall
                words = [w for w in clean_fts_query.split() if len(w) > 1]
                if words:
                    fts_clause = " OR ".join(f'"{w}"*' for w in words)
                    try:
                        cur.execute("""
                            SELECT rowid, rank FROM chunks_fts
                            WHERE chunks_fts MATCH ?
                            ORDER BY rank
                            LIMIT 50
                        """, (fts_clause,))
                        rows = cur.fetchall()
                        # FTS5 rank is negative (lower = better), normalize to [0, 1]
                        if rows:
                            min_rank = min(r["rank"] for r in rows)
                            max_rank = max(r["rank"] for r in rows)
                            span = max(1e-6, max_rank - min_rank)
                            for r in rows:
                                # Invert so higher is better
                                fts_scores[r["rowid"]] = 1.0 - ((r["rank"] - min_rank) / span)
                    except sqlite3.OperationalError:
                        pass

            # 2. Vector search across candidate or all chunks
            query_filter = ""
            params: List[Any] = []
            if filter_ext:
                query_filter = "AND d.extension = ?"
                params.append(filter_ext.lower() if filter_ext.startswith(".") else f".{filter_ext.lower()}")

            sql = f"""
                SELECT c.id, c.doc_id, c.chunk_index, c.content, c.embedding,
                       d.path, d.filename, d.extension
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
                WHERE 1=1 {query_filter}
            """
            cur.execute(sql, params)
            candidates = cur.fetchall()

            scored: List[Tuple[float, Dict[str, Any]]] = []
            for row in candidates:
                cid = row["id"]
                try:
                    vec = json.loads(row["embedding"])
                except Exception:
                    vec = []

                cos_sim = cosine_similarity(query_vec, vec)
                bm25_sim = fts_scores.get(cid, 0.0)

                # Composite score: 55% dense semantic similarity + 45% exact keyword match
                final_score = round(0.55 * cos_sim + 0.45 * bm25_sim, 4)

                scored.append((
                    final_score,
                    {
                        "chunk_id": cid,
                        "doc_id": row["doc_id"],
                        "filename": row["filename"],
                        "path": row["path"],
                        "extension": row["extension"],
                        "chunk_index": row["chunk_index"],
                        "score": final_score,
                        "dense_similarity": round(cos_sim, 4),
                        "bm25_score": round(bm25_sim, 4),
                        "snippet": row["content"],
                    }
                ))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:top_k]]

    def get_status(self) -> Dict[str, Any]:
        """Return knowledge base status and stats."""
        with self._lock, self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count, SUM(size_bytes) as total_size FROM documents;")
            doc_row = cur.fetchone()
            cur.execute("SELECT COUNT(*) as count FROM chunks;")
            chunk_row = cur.fetchone()

            db_size = self.db_path.stat().st_size if self.db_path.is_file() else 0

            return {
                "db_path": str(self.db_path),
                "total_documents": doc_row["count"] if doc_row else 0,
                "total_indexed_bytes": doc_row["total_size"] if doc_row and doc_row["total_size"] else 0,
                "total_chunks": chunk_row["count"] if chunk_row else 0,
                "db_file_size_bytes": db_size,
            }

    def clear(self) -> bool:
        """Clear all indexed documents and chunks."""
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM documents;")
            conn.execute("DELETE FROM chunks;")
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');")
            conn.commit()
        return True


# Global default instance
_RAG_INSTANCE: Optional[LocalRAG] = None


def get_rag() -> LocalRAG:
    global _RAG_INSTANCE
    if _RAG_INSTANCE is None:
        _RAG_INSTANCE = LocalRAG()
    return _RAG_INSTANCE
