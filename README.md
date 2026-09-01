# Railway Block Planner

A smart railway maintenance block planning system designed to help plan maintenance activities while considering train operations, timetable constraints, and potential conflicts.

> **Note on Data Sources:** The current prototype uses synthetic/mock datasets because live railway system access is unavailable. Any real API/database integration would require authorized access and would be implemented separately.

## Project Overview

Railway maintenance requires planned blocks or temporary restrictions on railway corridors. These blocks must be coordinated with train movements and other operational requirements.

This project aims to develop a centralized planning system that integrates railway operational data and assists in identifying suitable maintenance windows.

## Objectives

- Integrate railway data from different operational sources.
- Normalize and combine data into a unified format.
- Forecast train and goods movement requirements.
- Detect conflicts between maintenance blocks and train operations.
- Generate feasible maintenance block schedules.
- Optimize selected blocks based on operational constraints.
- Provide a simple interface for viewing and managing planned blocks.

## Planned System Flow

```text
Railway Data Sources
        ↓
Data Collection
        ↓
Validation & Normalization
        ↓
Data Integration
        ↓
Forecasting
        ↓
Block Planning
        ↓
Conflict Detection
        ↓
Optimization
        ↓
Final Maintenance Plan
```

---

## Phase 1 — Data Foundation (SMMS)

Phase 1 implemented the initial single-source ingestion pipeline for **SMMS** (Section Maintenance Management System) data:

```text
SMMS Mock CSV
      ↓
SMMS Collector      (reads CSV → raw dicts)
      ↓
SMMS Validator      (checks required fields, types, allowed values)
      ↓
SMMS Normalizer     (converts strings → native Python types)
      ↓
Unified Schema      (Pydantic MaintenanceRecord)
```

---

## Phase 2 — Multi-Source Data Integration (Current)

Phase 2 expands the pipeline into a full multi-source railway data integration system:

```text
                    ┌── TMS        (Train Management System)
                    ├── TDMS       (Train Data Management System)
                    ├── SMMS       (Section Maintenance Management System)
                    ├── COA        (Control Office Application)
                    ├── BDMS       (Block Data Management System)
                    └── Timetable  (Scheduled Train Movement Data)
                           ↓
                    Source Collectors
                           ↓
                    Source Validators
                           ↓
                       Normalizers
                           ↓
                     Entity Mapper
                           ↓
                         Merger
                           ↓
                  Conflict Resolver
                           ↓
                  Unified Railway Dataset
```

### Integrated Sources

| Source | Role | Records in Prototype | Model Output |
|---|---|---|---|
| **TMS** | Train movement & live operational status | 12 | `TrainRecord` |
| **TDMS** | Train/traffic operational parameters & route data | 12 | `TrainRecord` |
| **SMMS** | Asset maintenance requirements & resources | 12 | `MaintenanceRecord` |
| **COA** | Section/corridor occupancy & movement | 12 | `MovementRecord` |
| **BDMS** | Block & disconnection planning requests | 12 | `BlockRecord` |
| **Timetable** | Scheduled multi-station train timetable | 39 | `TimetableRecord` |

### Key Components

- **Collectors**: Source acquisition modules that read CSV files and output plain dictionaries.
- **Validators**: Strict validation checking required fields, allowed enum-like values, and ISO date/time formats.
- **Normalizers**: Source-specific converters transforming raw strings into typed dictionaries.
- **Entity Mapper**: Deterministic entity grouping matching `train_id` across train sources and `location` across infrastructure/block sources.
- **Merger**: Combines multi-source operational data (e.g. TMS + TDMS for the same train) while preserving source provenance.
- **Conflict Resolver**: Resolves operational status disagreements using documented prototype precedence (`TMS > TDMS > Timetable > COA`) and logs detected conflicts.
- **RailwayDataIntegrator**: End-to-end multi-source pipeline orchestrator returning structured datasets and comprehensive statistics.

### Running the Phase 2 Demo

From the project root:

```bash
python -m backend.app.data_integration.integrator
```

To run the legacy Phase 1 SMMS demo:

```bash
python -m backend.app.data_integration.integrator --phase1
```

### Running Tests

```bash
pytest backend/tests/ -v
```

---

## Phase 3 — Database + Repositories + FastAPI (Current)

Phase 3 persists the unified multi-source dataset into a relational database via SQLAlchemy and exposes the domain entities through FastAPI RESTful API endpoints.

```text
PHASE 3 ARCHITECTURE
====================

         Phase 2 Integration Output
                     ↓
           RailwayDataIntegrator
                     ↓
            Unified Domain Data
                     ↓
         ┌───────────────────────┐
         │   Repository Layer    │
         │ (CRUD & Query logic)  │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │  SQLAlchemy Database  │
         │ (SQLite / PostgreSQL) │
         │   • Trains            │
         │   • Maintenance       │
         │   • Movements         │
         │   • Blocks            │
         │   • Timetable         │
         └───────────┬───────────┘
                     ↓
         ┌───────────────────────┐
         │  FastAPI REST Server  │
         └───────────┬───────────┘
                     ↓
  ┌──────────────┬───┴──────────┬──────────────┐
  ▼              ▼              ▼              ▼
Trains     Maintenance        Blocks         Plans
 API            API            API            API
```

### Key Components

- **Database Models (`backend/app/database/models.py`)**: Persistent SQLAlchemy ORM representations of `Train`, `Maintenance`, `Movement`, `Block`, and `Timetable` entities mapped directly from Phase 2 canonical schemas.
- **Repository Layer (`backend/app/database/repositories.py`)**: Encapsulated data access objects (`TrainRepository`, `MaintenanceRepository`, `MovementRepository`, `BlockRepository`, `TimetableRepository`) with CRUD, filtering, pagination, and specialized queries.
- **Database Seeding CLI (`backend/app/database/seed.py`)**: Automated pipeline execution feeding Phase 2 `RailwayDataIntegrator` outputs into database tables idempotently.
- **FastAPI Application (`backend/app/main.py`)**: REST server providing CORS, lifespan management, health checks, dependency injection, and interactive Swagger documentation at `/docs`.
- **REST Endpoints (`backend/app/api/routes/`)**:
  - `GET /health` — Service health & database connectivity
  - `GET /api/trains` & `GET /api/trains/{train_id}` — Query train status & route metadata
  - `GET /api/maintenance` & `GET /api/maintenance/{asset_id}` — Query maintenance requirements & priorities
  - `GET /api/blocks` & `GET /api/blocks/{block_id}` — Query track disconnection requests
  - `GET /api/plans` — Read-only persistent block plan view

### Running Phase 3

#### 1. Seed Database

```bash
python -m backend.app.database.seed
```

To drop and recreate all tables before seeding:

```bash
python -m backend.app.database.seed --reset
```

#### 2. Start FastAPI Server

```bash
uvicorn backend.app.main:app --reload
```

Interactive API documentation (Swagger UI) is available at:
```text
http://localhost:8000/docs
```

#### 3. Run Tests

```bash
pytest backend/tests/ -v
```

### Project Structure (Phase 3)

```text
railway-block-planner/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── blocks.py
│   │   │   │   ├── maintenance.py
│   │   │   │   ├── plans.py
│   │   │   │   └── trains.py
│   │   │   └── dependencies.py
│   │   ├── data_integration/
│   │   │   ├── collectors/
│   │   │   │   ├── smms_collector.py
│   │   │   │   ├── tms_collector.py
│   │   │   │   ├── tdms_collector.py
│   │   │   │   ├── coa_collector.py
│   │   │   │   ├── bdms_collector.py
│   │   │   │   └── timetable_provider.py
│   │   │   ├── validators/
│   │   │   │   ├── smms_validator.py
│   │   │   │   ├── tms_validator.py
│   │   │   │   ├── tdms_validator.py
│   │   │   │   ├── coa_validator.py
│   │   │   │   ├── bdms_validator.py
│   │   │   │   └── timetable_validator.py
│   │   │   ├── normalizer.py
│   │   │   ├── entity_mapper.py
│   │   │   ├── merger.py
│   │   │   ├── conflict_resolver.py
│   │   │   └── integrator.py
│   │   ├── database/
│   │   │   ├── connection.py
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   └── seed.py
│   │   ├── schemas/
│   │   │   └── unified_data.py
│   │   └── main.py
│   └── tests/
│       ├── test_collectors.py
│       ├── test_validators.py
│       ├── test_normalizer.py
│       ├── test_entity_mapper.py
│       ├── test_merger.py
│       ├── test_conflict_resolver.py
│       ├── test_integrator.py
│       ├── test_database.py
│       ├── test_repositories.py
│       ├── test_seed.py
│       └── test_api.py
├── data/
│   └── raw/
│       ├── smms/mock_smms.csv
│       ├── tms/mock_tms.csv
│       ├── tdms/mock_tdms.csv
│       ├── coa/mock_coa.csv
│       ├── bdms/mock_bdms.csv
│       └── timetable/mock_timetable.csv
├── config/
│   └── source_config.yaml
├── .env.example
├── docker-compose.yml
└── requirements.txt
```