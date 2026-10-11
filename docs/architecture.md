# InfraPM Intelligence Architecture

## High-Level System Architecture

```mermaid
flowchart TD
    subgraph Client Layer
        UI[React / TypeScript Frontend\n(Vite)]
    end

    subgraph API Layer
        API[FastAPI Router\n(Auth, Validation, DI)]
    end

    subgraph Service Layer
        AuthSvc[Auth Service]
        ProjSvc[Project & Contract Services]
        BoqSvc[BOQ Service]
        MeasSvc[Measurement Service]
        BillSvc[RA Billing Service]
        EotSvc[EOT Service]
        EvmSvc[EVM Service]
        DocSvc[Document Intelligence Service]
    end

    subgraph Data Access Layer
        ORM[SQLAlchemy ORM]
    end

    subgraph Storage Layer
        DB[(PostgreSQL)]
    end

    UI -->|HTTPS / REST| API
    API --> AuthSvc
    API --> ProjSvc
    API --> BoqSvc
    API --> MeasSvc
    API --> BillSvc
    API --> EotSvc
    API --> EvmSvc
    API --> DocSvc

    AuthSvc --> ORM
    ProjSvc --> ORM
    BoqSvc --> ORM
    MeasSvc --> ORM
    BillSvc --> ORM
    EotSvc --> ORM
    EvmSvc --> ORM
    DocSvc --> ORM

    ORM --> DB
```

## Document Intelligence & Ingestion Flow

The current platform implements a deterministic ingestion and reconciliation pipeline for core documents (Contracts, BOQs, Measurements, RA Bills).

```mermaid
flowchart LR
    Upload[Document Upload\n(PDF/XLSX)] --> Parse[Pattern-Based Extractor\n(Regex / Pandas)]
    Parse --> Validate[Structural Validation\n(Pydantic)]
    Validate --> Reconcile[Canonical Reconciliation\n(Entity Matching)]
    Reconcile --> Persist[Database Persistence]

    subgraph Planned Capabilities
        LLM[LLM / GenAI Fallback]
        VectorDB[(Vector Embeddings\nfor RAG)]
    end

    Parse -.->|Fallback| LLM
    Persist -.->|Embed| VectorDB
```

## Earned Value Management (EVM) Flow

```mermaid
flowchart TD
    Contract[Contract Value & Timeline] --> Baseline[EVM Baseline\n(Planned Value Curve)]
    Measurements[Approved Measurements] --> RABill[RA Billing]

    Baseline --> Engine[EVM Calculation Engine]
    RABill --> Engine

    Engine --> Metrics[Period Metrics\n(PV, EV, AC, SPI, CPI)]

    subgraph Planned Capabilities
        Predictive[Predictive Forecasting\n(Cost/Schedule Overruns)]
    end

    Metrics -.-> Predictive
```
