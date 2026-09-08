"""Generates Excel reports with 4 sheets:

Results (best offer per supplier/warehouse), Raw Data (all offers),
Errors (all errors with attempt count), Settings (run metadata).
"""

from datetime import datetime
from pathlib import Path

import openpyxl
from loguru import logger
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from foxprice.core.models import ErrorResult, PricedResult, RunSummary

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)


class Reporter:
    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        priced: list[PricedResult],
        errors: list[ErrorResult],
        summary: RunSummary,
    ) -> Path:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        results_ws = wb.create_sheet("Results")
        results_headers = [
            "Supplier",
            "Part Number",
            "Matched Part",
            "Unit Price",
            "Markup %",
            "Final Price",
            "Currency",
            "Warehouse",
            "Lead Time (days)",
            "Pack Size",
            "MOQ",
            "Fuzzy Matched",
        ]
        self._apply_headers(results_ws, results_headers)
        for pr in priced:
            offer = pr.offer
            results_ws.append(
                [
                    offer.supplier,
                    offer.part_number,
                    offer.matched_part,
                    str(offer.unit_price),
                    str(pr.markup_pct),
                    str(pr.final_price),
                    offer.currency,
                    offer.warehouse_label or offer.warehouse_code,
                    offer.lead_time_days,
                    offer.pack_size,
                    offer.min_order_qty,
                    offer.fuzzy_matched,
                ]
            )
        self._autosize(results_ws)

        # Raw Data mirrors `priced`, so only offers that made it through
        # pricing are listed here. Offers an adapter returned but that
        # never got priced (e.g. rfq_only=True) are not represented on
        # any sheet in this v1 report.
        raw_ws = wb.create_sheet("Raw Data")
        raw_headers = [
            "Supplier",
            "Part Number",
            "Matched Part",
            "Unit Price",
            "Currency",
            "Warehouse",
            "Lead Time (days)",
            "Pack Size",
            "MOQ",
            "Fuzzy Matched",
        ]
        self._apply_headers(raw_ws, raw_headers)
        for pr in priced:
            offer = pr.offer
            raw_ws.append(
                [
                    offer.supplier,
                    offer.part_number,
                    offer.matched_part,
                    str(offer.unit_price),
                    offer.currency,
                    offer.warehouse_label or offer.warehouse_code,
                    offer.lead_time_days,
                    offer.pack_size,
                    offer.min_order_qty,
                    offer.fuzzy_matched,
                ]
            )
        self._autosize(raw_ws)

        errors_ws = wb.create_sheet("Errors")
        errors_headers = [
            "Supplier",
            "Part Number",
            "Error Type",
            "Description",
            "Attempt",
            "Timestamp",
        ]
        self._apply_headers(errors_ws, errors_headers)
        for err in errors:
            errors_ws.append(
                [
                    err.supplier,
                    err.part_number,
                    err.error_type,
                    err.description,
                    err.attempt,
                    err.timestamp.isoformat(),
                ]
            )
        self._autosize(errors_ws)

        settings_ws = wb.create_sheet("Settings")
        self._apply_headers(settings_ws, ["Key", "Value"])
        settings_rows = [
            ("Run ID", summary.run_id),
            ("Parts Total", summary.parts_total),
            ("Parts Found", summary.parts_found),
            ("Parts Not Found", summary.parts_not_found),
            ("Errors", summary.errors),
            ("Duration (sec)", summary.duration_sec),
            ("Suppliers", ", ".join(summary.suppliers)),
            ("Generated At (UTC)", datetime.utcnow().isoformat()),
        ]
        for row in settings_rows:
            settings_ws.append(row)
        self._autosize(settings_ws)

        path = self.output_dir / f"foxprice_{summary.run_id}.xlsx"
        wb.save(path)
        logger.info(f"report saved: {path}")
        return path

    def _apply_headers(self, ws: Worksheet, headers: list[str]) -> None:
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT

    def _autosize(self, ws: Worksheet) -> None:
        for column_cells in ws.columns:
            length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
            col_letter = column_cells[0].column_letter
            ws.column_dimensions[col_letter].width = min(length + 4, 50)
