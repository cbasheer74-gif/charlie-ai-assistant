"""engine/agents/spreadsheet_agent.py — Programmatic Excel and Spreadsheet Specialist.

Uses openpyxl for reliable workbook operations, formula preservation, duplicate removal,
summary sheet generation, and copy-first output safety.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class SpreadsheetAgent(BaseAgent):
    """Specialist agent for Excel (.xlsx/.xlsm) and CSV files."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("excel", "sheet", "spreadsheet", ".xlsx", ".csv", "clean workbook", "summary sheet"))

    def inspect_workbook(self, file_path: Path | str) -> Dict[str, Any]:
        """Inspect sheet names, dimensions, headers, and formula count."""
        from openpyxl import load_workbook
        p = Path(file_path).resolve()
        wb = load_workbook(p, data_only=False)
        sheet_info = []
        formula_total = 0
        for name in wb.sheetnames:
            ws = wb[name]
            f_count = sum(1 for row in ws.iter_rows(values_only=False) for c in row if c.value and str(c.value).startswith("="))
            formula_total += f_count
            sheet_info.append({
                "name": name,
                "max_row": ws.max_row,
                "max_col": ws.max_column,
                "formulas": f_count,
            })
        return {
            "file": p.name,
            "sheets": sheet_info,
            "total_formulas": formula_total,
        }

    def clean_workbook(self, file_path: Path | str, output_path: Optional[Path | str] = None) -> Dict[str, Any]:
        """Clean workbook: strip whitespace, remove duplicate rows, preserve formulas, and verify."""
        from openpyxl import load_workbook
        p = Path(file_path).resolve()
        self.rollback.backup_file(p)

        wb = load_workbook(p, data_only=False)
        modified_sheets = 0
        cleaned_cells = 0

        for sname in wb.sheetnames:
            ws = wb[sname]
            seen_rows = set()
            rows_to_delete = []

            for r_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
                row_vals = []
                for cell in row:
                    val = cell.value
                    if isinstance(val, str) and not val.startswith("="):
                        stripped = val.strip()
                        if stripped != val:
                            cell.value = stripped
                            cleaned_cells += 1
                        row_vals.append(stripped)
                    else:
                        row_vals.append(val)

                # Skip header row (row 1) for duplicate checks
                if r_idx > 1 and any(row_vals):
                    row_key = tuple(str(x) for x in row_vals)
                    if row_key in seen_rows:
                        rows_to_delete.append(r_idx)
                    else:
                        seen_rows.add(row_key)

            # Delete duplicate rows bottom-to-top so row indices stay stable
            for del_idx in reversed(rows_to_delete):
                ws.delete_rows(del_idx)
                modified_sheets += 1

        dest = Path(output_path).resolve() if output_path else p
        wb.save(dest)

        # Verification
        ok, v_msg = self.verification.verify_excel(dest)
        return {
            "status": "success" if ok else "warning",
            "destination": str(dest),
            "cleaned_cells": cleaned_cells,
            "verification": v_msg,
        }

    def create_summary_sheet(self, file_path: Path | str, target_sheet: Optional[str] = None) -> Dict[str, Any]:
        """Generate a dedicated summary sheet with totals, averages, and counts."""
        from openpyxl import load_workbook
        p = Path(file_path).resolve()
        self.rollback.backup_file(p)

        wb = load_workbook(p, data_only=False)
        src_ws = wb[target_sheet] if target_sheet and target_sheet in wb.sheetnames else wb.active
        summary_name = "Summary"
        if summary_name in wb.sheetnames:
            del wb[summary_name]
        sum_ws = wb.create_sheet(title=summary_name)

        # Headers
        sum_ws.cell(row=1, column=1, value="Metric")
        sum_ws.cell(row=1, column=2, value="Formula / Value")

        row_cursor = 2
        sum_ws.cell(row=row_cursor, column=1, value="Source Sheet")
        sum_ws.cell(row=row_cursor, column=2, value=src_ws.title)
        row_cursor += 1

        sum_ws.cell(row=row_cursor, column=1, value="Total Data Rows")
        sum_ws.cell(row=row_cursor, column=2, value=f"=COUNTA('{src_ws.title}'!A:A)-1")
        row_cursor += 1

        # Scan for numeric columns
        for c_idx in range(1, min(src_ws.max_column + 1, 20)):
            col_letter = chr(ord('A') + c_idx - 1) if c_idx <= 26 else 'A'
            header = str(src_ws.cell(row=1, column=c_idx).value or f"Col_{c_idx}")
            sum_ws.cell(row=row_cursor, column=1, value=f"Sum of {header}")
            sum_ws.cell(row=row_cursor, column=2, value=f"=SUM('{src_ws.title}'!{col_letter}2:{col_letter}{src_ws.max_row})")
            row_cursor += 1

        wb.save(p)
        ok, v_msg = self.verification.verify_excel(p, expected_sheets=["Summary"])
        return {
            "status": "success" if ok else "failed",
            "file": str(p),
            "summary_sheet": summary_name,
            "verification": v_msg,
        }
