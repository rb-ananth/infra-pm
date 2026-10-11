# InfraPM Intelligence Architecture

## High-Level System Architecture

```mermaid
flowchart TD
    subgraph Client["Client Layer"]
        UI["React / TypeScript Frontend (Vite)"]
    end

    subgraph Backend["Backend Layer"]
        API["FastAPI REST API"]
        Services["Service Layer"]
    end

    subgraph Data["Data Layer"]
        ORM["SQLAlchemy ORM"]
        DB[("PostgreSQL + pgvector")]
    end

    UI --> API
    API --> Services
    Services --> ORM
    ORM --> DB
```

## Document Intelligence & Ingestion Flow

The current platform implements a deterministic ingestion and reconciliation pipeline for core documents (Contracts, BOQs, Measurements, RA Bills).

```mermaid
flowchart LR
    Upload["Document Upload (PDF / XLSX)"]
    Parse["Pattern-Based Extraction"]
    Validate["Structured Validation"]
    Reconcile["Entity Matching and Reconciliation"]
    Persist[("PostgreSQL Persistence")]

    Upload --> Parse
    Parse --> Validate
    Validate --> Reconcile
    Reconcile --> Persist

    Upload -.-> RAG["RAG Pipeline"]
    RAG --> Embeddings["Embedding Generation"]
    Embeddings --> VectorDB[("Vector Search")]
```

## Earned Value Management (EVM) Flow

```mermaid
flowchart TD
    Contract["Contract Value and Timeline"]
    Baseline["EVM Baseline"]
    Measurements["Approved Measurements"]
    RABill["RA Billing"]
    Engine["EVM Calculation Engine"]
    Metrics["PV, EV, AC, SPI and CPI"]

    Contract --> Baseline
    Measurements --> RABill
    Baseline --> Engine
    RABill --> Engine
    Engine --> Metrics
```
