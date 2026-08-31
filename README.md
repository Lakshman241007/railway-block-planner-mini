# Railway Block Planner

A smart railway maintenance block planning system designed to help plan maintenance activities while considering train operations, timetable constraints, and potential conflicts.

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

## Phase 1 — Data Foundation (Current)

Phase 1 implements a complete data-ingestion pipeline for **SMMS** (Section Maintenance Management System) data:

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

### Key Points

- **SMMS** represents a maintenance-management data source used by railway sections to track and plan maintenance activities on assets such as tracks, signals, bridges, and overhead equipment.
- The current prototype uses **synthetic / mock data** (`data/raw/smms/mock_smms.csv`). This data is entirely fictional and was created for prototype development purposes only.
- **Real API or database integration is NOT currently available.** The system does not connect to any live railway network.
- The collector architecture is designed so that an authorized API source or database connection could **replace the mock CSV** in the future without changing the downstream pipeline.
- The **unified schema** (`MaintenanceRecord`) is the contract used by all future modules. It is intentionally kept generic so that additional data sources (TMS, TDMS, COA, BDMS, timetable data) can eventually produce the same model.

### Running the Phase 1 Demo

From the project root:

```bash
python -m backend.app.data_integration.integrator
```

### Running Tests

```bash
pytest backend/tests/ -v
```

### Project Structure (Phase 1)

```text
railway-block-planner/
├── backend/
│   ├── app/
│   │   ├── data_integration/
│   │   │   ├── collectors/
│   │   │   │   └── smms_collector.py    ← CSV reader
│   │   │   ├── validators/
│   │   │   │   └── smms_validator.py    ← field validation
│   │   │   ├── normalizer.py           ← type conversion
│   │   │   └── integrator.py           ← end-to-end pipeline
│   │   └── schemas/
│   │       └── unified_data.py          ← Pydantic models
│   └── tests/
│       ├── test_collectors.py
│       ├── test_validators.py
│       ├── test_normalizer.py
│       └── test_integrator.py
├── data/
│   └── raw/
│       └── smms/
│           └── mock_smms.csv            ← synthetic data
├── config/
│   └── source_config.yaml              ← SMMS source config
└── requirements.txt
```