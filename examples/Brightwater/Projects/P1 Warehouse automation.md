---
type: project
id: P1
status: active
owner: Priya Shah
started: 2026-10-05
---
# P1 Warehouse automation

## Goal

Automated picking at the Riverside warehouse by summer 2027, cutting the cost per order by at least 15 percent.

## Why it matters

The cost per order rose 11 percent in a year, mostly through overtime, and the next peak season will need more of it.

## Next step

Priya Shah sends the vendor shortlist to the CFO; it was due on 16 October.

## Map

```mermaid
flowchart LR
    T["Today: 18,000 orders a day, picked by hand"] --> S["Vendor shortlist (M1)"]
    S --> D["Choose the system (D1) within a budget (D2)"]
    D --> B["Business case to the board (M2)"]
    B --> P["Pilot after the peak season (R1)"]
    P --> G["Cost per order down 15% (A1)"]
```

<!-- generated -->
## From the registers

### Decisions

| ID | Decision | Owner | Due | Status |
|---|---|---|---|---|
| [D2](../Knowledge/Decisions.md) | The capital envelope for warehouse automation: up to £4m | Tom Becker | 2026-11-30 | open |
| [D1](../Knowledge/Decisions.md) | Which picking system: cube storage, shuttle racking, or wait a year | Alex Morgan | 2026-12-15 | open |
| [D4](../Knowledge/Decisions.md) | One cost model for both projects, and who builds it | Tom Becker |  | open |

### Risks

| ID | Risk | Level | Owner | Status |
|---|---|---|---|---|
| [R1](../Knowledge/Risks.md) | The peak season leaves no room to install before January | high | Priya Shah | open |

### Milestones

| ID | Milestone | Owner | Due | Status |
|---|---|---|---|---|
| [M1](../Knowledge/Milestones.md) | Vendor shortlist to the CFO | Priya Shah | 2026-10-16 | open |
| [M2](../Knowledge/Milestones.md) | The board approves the automation business case | Alex Morgan | 2026-12-10 | open |

### Assumptions

| ID | Assumption | Status |
|---|---|---|
| [A1](../Knowledge/Assumptions.md) | Automated picking cuts the cost per order by at least 15 percent | open |

### Issues

| ID | Issue | Status |
|---|---|---|
| [I1](../Knowledge/Current%20State.md) | The cost per order rose 11 percent in a year, mostly overtime | open |

### People

| Person | Role | Interests |
|---|---|---|
| Priya Shah | Head of Warehousing | A vendor decision before peak planning; a clear budget |
| Tom Becker | CFO | Payback under three years; one cost model for both projects |

### Meetings

- [2026-10-19 Warehouse vendors](../Meetings/2026-10-19%20Warehouse%20vendors.md)
- [2026-10-12 Weekly with the CFO](../Meetings/2026-10-12%20Weekly%20with%20the%20CFO.md)
- [2026-10-05 Setup](../Meetings/2026-10-05%20Setup.md)
<!-- /generated -->
