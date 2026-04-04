"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Download, FileText, FileJson, Printer } from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface Column {
  key: string;
  label: string;
}

interface ExportMenuProps {
  data: Record<string, unknown>[];
  filename: string;
  columns: Column[];
  title?: string;
}

// ── CSV helpers ──────────────────────────────────────────────────────────────

function escapeCsvValue(value: unknown): string {
  const str = value == null ? "" : String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function toCsv(data: Record<string, unknown>[], columns: Column[]): string {
  const header = columns.map((c) => escapeCsvValue(c.label)).join(",");
  const rows = data.map((row) =>
    columns.map((c) => escapeCsvValue(row[c.key])).join(",")
  );
  return [header, ...rows].join("\n");
}

// ── Download trigger ─────────────────────────────────────────────────────────

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── PDF / Print ──────────────────────────────────────────────────────────────

function printReport(
  data: Record<string, unknown>[],
  columns: Column[],
  title: string
) {
  const now = new Date().toLocaleString();

  // Compute summary statistics for numeric columns
  const summaryRows: string[] = [];
  columns.forEach((col) => {
    const nums = data
      .map((r) => r[col.key])
      .filter((v): v is number => typeof v === "number");
    if (nums.length > 0) {
      const sum = nums.reduce((a, b) => a + b, 0);
      const avg = sum / nums.length;
      const min = Math.min(...nums);
      const max = Math.max(...nums);
      summaryRows.push(
        `<tr>
          <td style="padding:6px 12px;font-weight:600;color:#fff;">${col.label}</td>
          <td style="padding:6px 12px;color:#aaa;">${nums.length}</td>
          <td style="padding:6px 12px;color:#aaa;">${min.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
          <td style="padding:6px 12px;color:#aaa;">${max.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
          <td style="padding:6px 12px;color:#aaa;">${avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
          <td style="padding:6px 12px;color:#aaa;">${sum.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
        </tr>`
      );
    }
  });

  const headerCells = columns
    .map(
      (c) =>
        `<th style="padding:8px 12px;text-align:left;border-bottom:1px solid #333;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">${c.label}</th>`
    )
    .join("");

  const bodyRows = data
    .map(
      (row, i) =>
        `<tr style="background:${i % 2 === 0 ? "#0a0a0a" : "#111"};">` +
        columns
          .map(
            (c) =>
              `<td style="padding:8px 12px;color:#ddd;font-size:12px;font-family:'SF Mono',Consolas,monospace;border-bottom:1px solid #1a1a1a;">${
                row[c.key] != null ? String(row[c.key]) : ""
              }</td>`
          )
          .join("") +
        "</tr>"
    )
    .join("");

  const summaryHtml =
    summaryRows.length > 0
      ? `<div style="margin-top:32px;">
          <h2 style="color:#fff;font-size:14px;margin-bottom:12px;font-family:system-ui;">Summary Statistics</h2>
          <table style="width:100%;border-collapse:collapse;border:1px solid #1a1a1a;">
            <thead>
              <tr style="background:#0a0a0a;">
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Column</th>
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Count</th>
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Min</th>
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Max</th>
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Avg</th>
                <th style="padding:6px 12px;text-align:left;color:#888;font-size:10px;text-transform:uppercase;">Sum</th>
              </tr>
            </thead>
            <tbody>${summaryRows.join("")}</tbody>
          </table>
        </div>`
      : "";

  const html = `
<!DOCTYPE html>
<html>
<head>
  <title>${title} — Lumare Report</title>
  <style>
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    body { margin:0; padding:40px; background:#080808; font-family:system-ui,-apple-system,sans-serif; }
  </style>
</head>
<body>
  <div style="margin-bottom:32px;border-bottom:1px solid #1a1a1a;padding-bottom:20px;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
      <div style="width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,#22c55e,#16a34a);display:flex;align-items:center;justify-content:center;">
        <span style="color:#fff;font-weight:bold;font-size:16px;">L</span>
      </div>
      <span style="color:#fff;font-size:20px;font-weight:700;letter-spacing:-0.5px;">Lumare</span>
    </div>
    <h1 style="color:#fff;font-size:18px;margin:8px 0 4px;">${title}</h1>
    <p style="color:#666;font-size:12px;margin:0;">Generated ${now} &middot; ${data.length} records</p>
  </div>

  <table style="width:100%;border-collapse:collapse;border:1px solid #1a1a1a;">
    <thead>
      <tr style="background:#0a0a0a;">${headerCells}</tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  </table>

  ${summaryHtml}

  <div style="margin-top:32px;padding-top:16px;border-top:1px solid #1a1a1a;color:#444;font-size:10px;">
    Lumare &middot; Confidential &middot; ${now}
  </div>
</body>
</html>`;

  const printWindow = window.open("", "_blank");
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.onload = () => {
      printWindow.print();
    };
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export function ExportMenu({ data, filename, columns, title }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const exportCsv = useCallback(() => {
    const csv = toCsv(data, columns);
    downloadBlob(csv, `${filename}.csv`, "text/csv;charset=utf-8;");
    setOpen(false);
  }, [data, columns, filename]);

  const exportJson = useCallback(() => {
    const mapped = data.map((row) => {
      const obj: Record<string, unknown> = {};
      columns.forEach((c) => {
        obj[c.label] = row[c.key];
      });
      return obj;
    });
    downloadBlob(JSON.stringify(mapped, null, 2), `${filename}.json`, "application/json");
    setOpen(false);
  }, [data, columns, filename]);

  const handlePrint = useCallback(() => {
    printReport(data, columns, title || filename);
    setOpen(false);
  }, [data, columns, title, filename]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg hover:bg-[#111] hover:border-[#333] transition-colors text-[#aaa]"
      >
        <Download className="w-3.5 h-3.5" />
        Export
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-48 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg shadow-2xl overflow-hidden">
          <button
            onClick={exportCsv}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-xs text-[#ccc] hover:bg-[#111] hover:text-white transition-colors"
          >
            <FileText className="w-4 h-4 text-[#22c55e]" />
            Export CSV
          </button>
          <button
            onClick={exportJson}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-xs text-[#ccc] hover:bg-[#111] hover:text-white transition-colors border-t border-[#1a1a1a]"
          >
            <FileJson className="w-4 h-4 text-[#3b82f6]" />
            Export JSON
          </button>
          <button
            onClick={handlePrint}
            className="w-full flex items-center gap-3 px-4 py-2.5 text-xs text-[#ccc] hover:bg-[#111] hover:text-white transition-colors border-t border-[#1a1a1a]"
          >
            <Printer className="w-4 h-4 text-[#a855f7]" />
            Print Report
          </button>
        </div>
      )}
    </div>
  );
}
