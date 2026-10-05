"""actions/rag_search.py — Auto-discovered action for Local RAG doc-search.

Allows CHARLIE voice and text agents to:
1. Search local documents with hybrid semantic + keyword retrieval.
2. Index individual documents or entire directories into the local knowledge base.
3. Inspect document index status and statistics.
4. Clear or reset the knowledge base.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from engine.rag import get_rag


def rag_search(parameters: Dict[str, Any], **kwargs) -> str:
    """Handle RAG search and indexing actions."""
    action = str(parameters.get("action") or "search").strip().lower()
    rag = get_rag()

    if action == "search":
        query = str(parameters.get("query") or "").strip()
        if not query:
            return "Please provide a query to search local documents."

        limit = int(parameters.get("limit") or 3)
        limit = max(1, min(10, limit))

        results = rag.search(query, top_k=limit)
        if not results:
            return f"No relevant document snippets found for '{query}'."

        lines = [f"Found {len(results)} relevant snippet(s) for '{query}':\n"]
        for idx, res in enumerate(results, 1):
            filename = res["filename"]
            score = int(res["score"] * 100)
            snippet = res["snippet"].strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:280] + "..."
            lines.append(f"{idx}. [{filename}] (Relevance: {score}%)\n   \"{snippet}\"\n   Source: {res['path']}")

        return "\n\n".join(lines)

    if action == "index":
        path_str = str(parameters.get("path") or "").strip().strip('"')
        if not path_str:
            return "Please specify a file or folder path to index."

        target = Path(path_str).resolve()
        if not target.exists():
            return f"Path does not exist: {target}"

        if target.is_file():
            res = rag.index_file(target)
            st = res.get("status")
            if st == "indexed":
                return f"Successfully indexed '{target.name}' ({res.get('chunks')} chunks)."
            elif st == "up_to_date":
                return f"File '{target.name}' is already up to date."
            else:
                return f"Could not index '{target.name}': {res.get('reason', res.get('error'))}"

        if target.is_dir():
            recursive = bool(parameters.get("recursive", True))
            res = rag.index_directory(target, recursive=recursive)
            return (
                f"Directory indexing finished for '{target.name}':\n"
                f"- Indexed: {res.get('indexed_files')} new file(s) ({res.get('total_new_chunks')} chunks)\n"
                f"- Skipped: {res.get('skipped_files')} unchanged/unsupported file(s)\n"
                f"- Errors: {res.get('failed_files')} file(s)"
            )

    if action == "status":
        stats = rag.get_status()
        kb_size_kb = round(stats.get("db_file_size_bytes", 0) / 1024, 1)
        return (
            f"Local RAG Status:\n"
            f"- Total Documents: {stats.get('total_documents')}\n"
            f"- Total Chunks: {stats.get('total_chunks')}\n"
            f"- Database Size: {kb_size_kb} KB\n"
            f"- Store Path: {stats.get('db_path')}"
        )

    if action == "clear":
        rag.clear()
        return "Local RAG knowledge base cleared successfully."

    return "Invalid action. Choose from: search, index, status, clear."


TOOL = {
    "name": "rag_search",
    "description": (
        "Search and retrieve answers from local files and indexed documents (PDF, Word, Markdown, Text, Code) "
        "using offline local RAG. Can also index new files or directories into memory on demand."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "search | index | status | clear",
            },
            "query": {
                "type": "STRING",
                "description": "Search query or question to lookup inside indexed local files",
            },
            "path": {
                "type": "STRING",
                "description": "File or folder path to index into local RAG",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Max snippets to return (default 3, max 10)",
            },
            "recursive": {
                "type": "BOOLEAN",
                "description": "Whether to index subdirectories when indexing a folder (default true)",
            },
        },
        "required": ["action"],
    },
    "handler": rag_search,
}
