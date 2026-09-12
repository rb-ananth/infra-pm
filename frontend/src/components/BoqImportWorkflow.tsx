import { useRef, useState } from "react";

import {
  boqApi,
  getApiErrorDetail,
  getApiErrorMessage,
} from "../services/api";
import type {
  BoqImportError,
  BoqImportPreview,
  BoqImportResult,
} from "../types";
import { formatInr } from "../utils/money";

const MAX_FILE_SIZE = 10 * 1024 * 1024;

type ImportStep = "select" | "preview" | "complete";

type BoqImportWorkflowProps = {
  revisionId: string;
  onClose: () => void;
  onImported: () => Promise<void>;
};

function normalizeErrors(detail: unknown): BoqImportError[] {
  if (!detail || typeof detail !== "object") return [];
  const payload = detail as { errors?: unknown };
  if (Array.isArray(payload.errors)) {
    return payload.errors.filter(
      (item): item is BoqImportError =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as BoqImportError).message === "string",
    );
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "object" && item !== null) {
        const row = typeof (item as { row?: unknown }).row === "number" ? (item as { row: number }).row : null;
        const field =
          typeof (item as { field?: unknown }).field === "string"
            ? (item as { field: string }).field
            : Array.isArray((item as { loc?: unknown }).loc)
              ? (item as { loc: unknown[] }).loc.filter((loc) => loc !== "body").join(".")
              : null;
        const message =
          typeof (item as { message?: unknown }).message === "string"
            ? (item as { message: string }).message
            : typeof (item as { msg?: unknown }).msg === "string"
              ? (item as { msg: string }).msg
              : JSON.stringify(item);
        return { row, field, message };
      }
      return { row: null, field: null, message: String(item) };
    });
  }
  return [];
}

function normalizeIgnoredColumns(detail: unknown): string[] {
  if (!detail || typeof detail !== "object") return [];
  const payload = detail as { ignored_columns?: unknown };
  if (!Array.isArray(payload.ignored_columns)) return [];
  return payload.ignored_columns.filter((item): item is string => typeof item === "string");
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function BoqImportWorkflow({
  revisionId,
  onClose,
  onImported,
}: BoqImportWorkflowProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<ImportStep>("select");
  const [preview, setPreview] = useState<BoqImportPreview | null>(null);
  const [result, setResult] = useState<BoqImportResult | null>(null);
  const [errors, setErrors] = useState<BoqImportError[]>([]);
  const [ignoredColumns, setIgnoredColumns] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [refreshWarning, setRefreshWarning] = useState("");
  const [busy, setBusy] = useState(false);

  function resetFileInput() {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function resetForNewFile() {
    resetFileInput();
    setFile(null);
    setPreview(null);
    setResult(null);
    setErrors([]);
    setIgnoredColumns([]);
    setErrorMessage("");
    setRefreshWarning("");
    setStep("select");
  }

  function selectFile(nextFile: File | null) {
    if (!nextFile) {
      resetFileInput();
      setFile(null);
      return;
    }
    resetForNewFile();
    const extension = nextFile.name.toLowerCase().split(".").pop();
    if (extension !== "csv" && extension !== "xlsx") {
      resetFileInput();
      setFile(null);
      setErrorMessage("Select a .csv or .xlsx file.");
      return;
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      resetFileInput();
      setFile(null);
      setErrorMessage("The selected file exceeds the 10 MB upload limit.");
      return;
    }
    setFile(nextFile);
  }

  async function previewFile() {
    if (!file) {
      setErrorMessage("Choose an Excel or CSV file first.");
      return;
    }
    try {
      setBusy(true);
      setErrorMessage("");
      setErrors([]);
      setIgnoredColumns([]);
      const response = await boqApi.previewImport(revisionId, file);
      setPreview(response.data);
      setIgnoredColumns(response.data.ignored_columns || []);
      setStep("preview");
      if (!response.data.valid) {
        setErrors(response.data.errors);
      }
    } catch (requestError) {
      setPreview(null);
      setErrorMessage(getApiErrorMessage(requestError, "Unable to preview this file."));
      const detail = getApiErrorDetail(requestError);
      setErrors(normalizeErrors(detail));
      setIgnoredColumns(normalizeIgnoredColumns(detail));
      setStep("preview");
    } finally {
      setBusy(false);
    }
  }

  async function importItems() {
    if (!file || !canImport) return;
    try {
      setBusy(true);
      setErrorMessage("");
      setRefreshWarning("");
      const response = await boqApi.importItems(revisionId, file);
      setResult(response.data);
      setStep("complete");
    } catch (requestError) {
      setErrorMessage(getApiErrorMessage(requestError, "Unable to import BOQ items."));
      setErrors(normalizeErrors(getApiErrorDetail(requestError)));
      setBusy(false);
      return;
    } finally {
      setBusy(false);
    }

    try {
      await onImported();
    } catch {
      setRefreshWarning(
        "Items were imported successfully, but updating the revision in the background failed. Refresh the page to see the latest data.",
      );
    }
  }

  const previewErrors = errors.length > 0 ? errors : (preview?.errors || []);
  const canImport = Boolean(preview?.valid) && previewErrors.length === 0;
  const activeIgnoredColumns = preview?.ignored_columns || ignoredColumns;

  return (
    <div className="modal-backdrop boq-modal-backdrop">
      <section className="card modal boq-import-modal" aria-labelledby="boq-import-title">
        <div className="modal-header">
          <div>
            <div className="eyebrow">Draft Revision</div>
            <h2 id="boq-import-title">Import BOQ Items</h2>
          </div>
          <button className="secondary" type="button" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>

        <div className="boq-import-steps" aria-label="Import progress">
          <span className={step === "select" ? "active" : "complete"}>1. Select File</span>
          <span className={step === "preview" ? "active" : step === "complete" ? "complete" : ""}>2. Preview</span>
          <span className={step === "complete" ? "active" : ""}>3. Complete</span>
        </div>

        {errorMessage && <div className="alert error">{errorMessage}</div>}

        {step === "select" && (
          <div className="boq-import-select">
            <label className="boq-file-dropzone">
              <span className="eyebrow">Excel / CSV source</span>
              <strong>{file ? "Replace selected file" : "Choose an Excel or CSV file"}</strong>
              <small>Accepted formats: .xlsx, .csv. Maximum size: 10 MB.</small>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) => selectFile(event.target.files?.[0] || null)}
              />
            </label>

            {file && (
              <div className="boq-selected-file">
                <div>
                  <strong>{file.name}</strong>
                  <span>{formatFileSize(file.size)}</span>
                </div>
                <button type="button" className="secondary" onClick={() => selectFile(null)}>
                  Remove
                </button>
              </div>
            )}

            <div className="form-actions">
              <button className="secondary" type="button" onClick={onClose} disabled={busy}>
                Cancel
              </button>
              <button type="button" onClick={previewFile} disabled={!file || busy}>
                {busy ? "Validating..." : "Preview Import"}
              </button>
            </div>
          </div>
        )}

        {step === "preview" && (
          <div className="boq-import-preview">
            {busy && <p className="muted">Validating file...</p>}

            {preview && (
              <div className="boq-import-summary">
                <div><span>Rows detected</span><strong>{preview.total_rows}</strong></div>
                <div><span>Items to import</span><strong>{preview.valid_rows}</strong></div>
                <div><span>Warnings</span><strong>{preview.warnings.length + activeIgnoredColumns.length}</strong></div>
                <div><span>Errors</span><strong>{previewErrors.length}</strong></div>
              </div>
            )}

            {preview && preview.warnings.length > 0 && (
              <div className="boq-import-feedback warning">
                <strong>Warnings</strong>
                <ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </div>
            )}

            {activeIgnoredColumns.length > 0 && (
              <div className="boq-import-feedback warning">
                <strong>Ignored columns</strong>
                <ul>{activeIgnoredColumns.map((column) => <li key={column}>{column}</li>)}</ul>
              </div>
            )}

            {previewErrors.length > 0 && (
              <div className="boq-import-feedback error">
                <strong>Validation errors</strong>
                <ul>
                  {previewErrors.map((item, index) => (
                    <li key={`${item.row}-${item.field}-${index}`}>
                      {item.row ? `Row ${item.row}${item.field ? ` · ${item.field}` : ""}: ` : item.field ? `${item.field}: ` : ""}{item.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {canImport && preview && (
              <div className="boq-import-review">
                <strong>Ready to import {preview.items.length} items</strong>
                <span className="muted">Amounts will be calculated by the server from quantity × rate.</span>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>#</th><th>Description</th><th>Unit</th><th>Quantity</th><th>Rate (₹)</th><th>Amount (₹)</th></tr></thead>
                    <tbody>{preview.items.slice(0, 8).map((item) => <tr key={item.item_number}><td>{item.item_number}</td><td>{item.description}</td><td>{item.unit}</td><td>{item.quantity}</td><td>₹{formatInr(item.rate)}</td><td>₹{formatInr(item.amount)}</td></tr>)}</tbody>
                  </table>
                  {preview.items.length > 8 && <small className="muted">Showing the first 8 items in the review.</small>}
                </div>
              </div>
            )}

            <div className="form-actions">
              <button className="secondary" type="button" onClick={resetForNewFile} disabled={busy}>Back</button>
              {canImport && (
                <button type="button" onClick={importItems} disabled={busy}>
                  {busy ? "Importing..." : "Import Items"}
                </button>
              )}
            </div>
          </div>
        )}

        {step === "complete" && result && (
          <div className="boq-import-complete">
            <div className="boq-import-success-mark">✓</div>
            <h3>Import complete</h3>
            <p>Successfully imported {result.imported_count} item{result.imported_count === 1 ? "" : "s"}.</p>
            <strong>Revision total: ₹{formatInr(result.total)}</strong>
            {refreshWarning && (
              <div className="boq-import-feedback warning">
                {refreshWarning}
              </div>
            )}
            <div className="form-actions"><button type="button" onClick={onClose}>Close</button></div>
          </div>
        )}
      </section>
    </div>
  );
}

export default BoqImportWorkflow;