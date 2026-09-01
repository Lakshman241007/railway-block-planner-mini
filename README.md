# Railway Block Planner

A smart railway maintenance block planning and mathematical optimization system designed to help plan maintenance activities while considering train operations, timetable constraints, freight forecasts, safety buffers, and resource capacities.

> [!NOTE]
> **Prototype Disclaimer:** The current prototype uses synthetic/mock datasets because live railway system access is unavailable. All optimization rules, buffer intervals, equipment capacities, and objective weights are prototype assumptions for the hackathon demonstration and are **NOT official railway operating rules or policies**.

---

## System Flow

```text
Railway Data Sources (SMMS, TMS, TDMS, COA, BDMS, Timetable)
                    ↓
        Validation & Normalization (Phase 1 & 2)
                    ↓
        Unified Relational Database & Repositories (Phase 3)
                    ↓
        Goods Train Forecaster & Spatial-Temporal Conflict Detector (Phase 4)
                    ↓
        CP-SAT Mathematical Optimizer (Phase 5)
                    ↓
        Optimized Weekly & Monthly Maintenance Possession Plan
```

---

## Phase 1–3 Recap

- **Phase 1 (Data Foundation)**: Ingested, validated, and normalized SMMS asset maintenance requests into canonical Pydantic schemas.
- **Phase 2 (Multi-Source Integration)**: Multi-source pipeline integrating TMS, TDMS, SMMS, COA, BDMS, and Timetable datasets with entity mapping, cross-source merging, and conflict resolution.
- **Phase 3 (Persistence & REST API)**: Relational database layer with SQLAlchemy ORM models, repositories, automated idempotent seeding, and FastAPI endpoints.

---

## Phase 4 — Forecasting, Heuristic Scheduling & Conflict Detection

Phase 4 introduced predictive operations and spatial-temporal conflict detection:
- **Goods Train Forecaster (`GoodsTrainForecaster`)**: Predictive forecasting of goods train movements with route-based section intervals and statistical confidence scoring.
- **Maintenance Scheduler (`MaintenanceScheduler`)**: Corridor free-window scanner finding feasible maintenance slots clear of passenger stops, active movements, approved blocks, and goods forecasts.
- **Conflict Detector (`ConflictDetector`)**: Spatial-temporal collision and safety buffer auditor categorizing severity (`Critical`, `High`, `Medium`, `Low`).
- **Auto Resolver (`AutoResolver`)**: Rule-based operational recommendations.

---

## Phase 5 — Block Planner + CP-SAT Mathematical Optimizer

Phase 5 builds an exact constraint satisfaction and mathematical optimization layer using **Google OR-Tools CP-SAT**. It takes maintenance requests, feasible candidate slots, train timetables, goods forecasts, track sections, and equipment constraints to produce an optimal possession plan.

```text
PHASE 5 OPTIMIZATION ARCHITECTURE
=================================

                OptimizationRequest
       (target_date, horizon_days, weights, etc.)
                        │
                        ▼
         Multi-Day Candidate Slot Scanner
    (Feasible time windows across 7-day/30-day horizon)
                        │
                        ▼
          CP-SAT Mathematical Formulation
 ┌────────────────────────────────────────────────────────┐
 │ Decision Variables:                                    │
 │   • x[request_id, slot_id] ∈ {0, 1}                    │
 │                                                        │
 │ Hard Constraints:                                      │
 │   1. Exact duration preservation                       │
 │   2. Feasible-window assignment (≤ 1 slot per request) │
 │   3. Exclusive track possession (no section overlap)   │
 │   4. Train movement protection (passenger & freight)   │
 │   5. Safety headway buffer (default: 15 mins)          │
 │   6. Equipment & specialized resource capacities       │
 │   7. Planning horizon bounds [D, D + H)                │
 │                                                        │
 │ Soft Multi-Objective Maximization:                     │
 │   Max: W_sched·N + W_prio·P - W_dev·Δ - W_dis·(1-fit) │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
                    OR-Tools CP-SAT Solver
             (Deterministic multi-worker engine)
                            │
                            ▼
                   OptimizationResult
   (OptimizedBlock[], UnscheduledBlock[], SolverStatistics)
```

---

### CP-SAT Mathematical Model

#### 1. Decision Variables
- For each maintenance request $i$ and candidate feasible slot $s \in \text{CandidateSlots}(i)$:
  $$x_{i, s} \in \{0, 1\}$$
  where $x_{i, s} = 1$ if request $i$ is assigned to slot $s$, and $0$ otherwise.

#### 2. Hard Constraints
1. **Slot Assignment Uniqueness:**
   $$\sum_{s \in \text{CandidateSlots}(i)} x_{i, s} \le 1 \quad \forall i$$
2. **Track Mutual Exclusion (No Location Overlap):**
   For any two slots $s_1 \in \text{Slots}(i), s_2 \in \text{Slots}(j)$ on overlapping physical track sections on the same date with temporal overlap $[start_1, end_1) \cap [start_2, end_2) \neq \emptyset$:
   $$x_{i, s_1} + x_{j, s_2} \le 1$$
3. **Equipment & Specialized Resource Capacity:**
   For any equipment type $E$ with capacity $C_E$ (e.g. *Track Tamper*, *OHE Car*) and any concurrent time point $t$:
   $$\sum_{(i, s) \in \text{Active}(E, t)} x_{i, s} \le C_E$$
4. **Train Movement Protection & Headway:**
   All candidate slots are pre-filtered to guarantee zero overlap with passenger train stops, active movements, approved blocks, and goods train forecasts plus safety headway buffer.
5. **Exact Duration Preservation:**
   $$\text{end}(s) - \text{start}(s) = \text{duration}(i)$$

#### 3. Soft Multi-Objective Function
$$\text{Maximize} \sum_{i, s} x_{i, s} \cdot \Big( W_{\text{scheduled}} + W_{\text{priority}}(\text{priority}_i) - W_{\text{deviation}} \cdot |\text{start}_s - \text{pref}_i| - W_{\text{disruption}} \cdot (1 - \text{fit}_s) \Big)$$

---

### Configurable Objective Weights & Capacities

Centralized in `config/constraints.yaml`:

| Parameter | Default Value | Description |
|---|---|---|
| `weight_scheduled` | `10000` | Reward for scheduling a maintenance request |
| `weight_priority_critical` | `5000` | Urgency bonus for Critical maintenance |
| `weight_priority_high` | `2500` | Urgency bonus for High maintenance |
| `weight_priority_medium` | `1000` | Urgency bonus for Medium maintenance |
| `weight_priority_low` | `200` | Urgency bonus for Low maintenance |
| `weight_preferred_deviation`| `5` | Penalty per minute shifted from preferred start |
| `weight_disruption` | `50` | Penalty for choosing lower-fit alternative slots |
| `safety.buffer_minutes` | `15` | Minimum clearance headway around train movements |
| `Track Tamper` capacity | `1` | Maximum concurrent tamper operations |
| `OHE Car` capacity | `1` | Maximum concurrent overhead line inspection cars |
| `Tower Wagon` capacity | `2` | Maximum concurrent tower wagon operations |

---

### Solver Statuses

The optimizer reports explicit solver statuses:
- **`OPTIMAL`**: Proven mathematically optimal solution found within time limit.
- **`FEASIBLE`**: Feasible valid schedule found satisfying all hard constraints.
- **`INFEASIBLE`**: Hard constraints cannot be simultaneously satisfied.
- **`UNKNOWN`**: Search stopped without determining feasibility (e.g., timeout before first solution).

---

### Weekly & Monthly Planning Horizons

The optimizer supports configurable planning windows with a unified mathematical engine:
- **Weekly Planning (7 days)**: `horizon_days: 7`
- **Monthly Planning (30 days)**: `horizon_days: 30`

---

## API Reference

### Phase 5 Optimization Endpoint

#### `POST /api/plans/optimize`

**Request Body:**
```json
{
  "target_date": "2026-09-01",
  "horizon_days": 7,
  "buffer_minutes": 15,
  "time_limit_seconds": 30.0,
  "num_workers": 4
}
```

**Example Response:**
```json
{
  "plan_id": "OPT-PLAN-A1B2C3D4",
  "generated_at": "2026-09-01T06:00:00Z",
  "target_date": "2026-09-01",
  "horizon_days": 7,
  "status": "OPTIMAL",
  "objective_value": 78450.0,
  "solver_statistics": {
    "status": "OPTIMAL",
    "objective_value": 78450.0,
    "wall_time_seconds": 0.042,
    "num_scheduled": 6,
    "num_unscheduled": 0,
    "num_conflicts_avoided": 14,
    "total_requests": 6,
    "num_variables": 24,
    "num_constraints": 18,
    "num_branches": 0
  },
  "scheduled_blocks": [
    {
      "block_id": "BLK-OPT-0001",
      "request_id": "TRK-M-001",
      "asset_id": "TRK-M-001",
      "location": "Chennai-Arakkonam",
      "service_date": "2026-09-01",
      "start_time": "02:00",
      "end_time": "04:00",
      "duration_minutes": 120,
      "priority": "Critical",
      "equipment": "Track Tamper",
      "required_resources": 2,
      "status": "Scheduled",
      "assigned_slot_id": "OPT-SLOT-0001",
      "fit_score": 1.0,
      "is_preferred_match": true,
      "deviation_minutes": 0
    }
  ],
  "unscheduled_blocks": [],
  "phase": "Phase 5 - CP-SAT Optimization",
  "notes": "Optimization rules and objective weights are prototype assumptions and NOT official railway operating rules."
}
```

---

## Running & Testing

### Run Tests

```bash
py -m pytest backend/tests/ -v
```

### Start API Server

```bash
uvicorn backend.app.main:app --reload
```

Interactive API documentation available at `http://localhost:8000/docs`.