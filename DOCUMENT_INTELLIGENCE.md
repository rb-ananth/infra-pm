# Document Intelligence V1

InfraPM Intelligence includes a robust Document Intelligence V1 feature focused on deterministic extraction and reconciliation of structured business facts from PDF and XLSX evidence.

## Capabilities

The current V1 implementation provides deterministic extraction for:
- **Contract Summaries** (PDF)
- **Bill of Quantities (BOQ)** (XLSX)
- **Measurement Books** (XLSX)
- **RA Bills** (XLSX)
- **Earned Value Management (EVM)** Progress Reports (PDF)

## EVM Evidence Extraction

The system processes monthly progress-report PDFs to extract EVM checkpoints:
- **PV (Planned Value)**
- **EV (Earned Value)**
- **AC (Actual Cost)**
- **Checkpoint Date**

### Source Validation vs. Canonical Reconciliation
The extraction service strictly separates data validation from canonical reconciliation:
1. **Validation**: The parser verifies structural integrity (e.g., proper decimals, absence of excessive precision, handling of duplicate observations within the same document). Invalid or ambiguous metrics (such as negative costs or overlapping EV fields) are flagged with `VALIDATION_ERRORS`, meaning the facts are successfully parsed but deemed structurally `INVALID`.
2. **Reconciliation**: Structurally valid facts are cross-referenced dynamically against the canonical `EVMService`. 
   - `MATCH`: Source evidence matches canonical calculations exactly.
   - `MISMATCH`: Source evidence disagrees with canonical calculations (e.g., a PDF mistakenly reports AC equal to EV on months without RA Bills, while the canonical logic accurately retains the previous baseline).
   - `NOT_COMPARABLE`: Missing critical context (e.g., missing checkpoint date) preventing any comparison.

### Canonical Calculation Rules
The canonical EVM baseline operates mathematically independently from the uploaded PDFs:
- **PV**: Derived from the approved EVM baseline schedule.
- **EV**: Derived from approved physical measurements valued at canonical BOQ rates.
- **AC**: Calculated as the cumulative value of approved RA Bills with a `bill_date` on or before the checkpoint date.

**Important Note**: Discrepancies between the PDF and canonical data (such as those intentionally planted in the July/August synthetic evidence) are *never* silently corrected or forcefully synchronized. The discrepancies are accurately captured as `MISMATCH` events in the `DocumentFact` metadata.

### Integrity & Idempotency
- **Provenance**: Extracted facts are tied immutably to the underlying `DocumentChunk` and `Document` via foreign keys.
- **Idempotency**: Running extraction multiple times over the exact same document is completely safe. The UUIDs of the facts are preserved, and identical duplicate processing is safely bypassed without triggering overlapping `AuditLog` events.
- **Transactional Rollback**: A failure during extraction (e.g., an error generating the audit log) instantly triggers an atomic rollback, guaranteeing that no partial or malformed `DocumentFact` structures are persisted.
- **Limitations**: The V1 extraction is currently strictly deterministic (Regex/Pandas). No LLMs, RAG, or semantic vector searches are applied, restricting processing strictly to defined text patterns.
