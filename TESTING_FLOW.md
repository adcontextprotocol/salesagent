# Testing & Simulation Flow

This document explains how to run the end-to-end simulation of the media buying lifecycle.

The simulation is orchestrated by the `simulation.py` script, which acts as the client (the "Orchestrator"). It communicates with the server (`main.py`) in local script mode, stepping through a predefined timeline of events.

## How it Works

The simulation uses a "fast-forward" mechanism. Instead of waiting for real time to pass, the client sends an optional `today` parameter with each request. The server uses this parameter as the current date for all its logic, including:
- Creative approval timelines
- Campaign flight dates
- Delivery pacing calculations

This allows us to simulate a month-long campaign in a few seconds.

## The Simulation Scenario

The `simulation.py` script executes the following sequence of events, printing the result of each step:

| Simulated Date | Action                               | Purpose                                                                 |
|----------------|--------------------------------------|-------------------------------------------------------------------------|
| **2025-06-15** | `get_proposal`                       | The client sends the initial brief and negotiates a proposal.           |
| **2025-06-18** | `accept_proposal`                    | The client accepts the proposal, creating a media buy on the server.    |
| **2025-06-22** | `add_creative_assets`                | Creatives are submitted for the campaign.                               |
| **2025-06-23** | `check_media_buy_status`             | Status is checked; creatives are still pending approval.                |
| **2025-06-24** | `check_media_buy_status`             | Status is checked again; creatives are now approved.                    |
| **2025-07-01** | `get_media_buy_delivery`             | Campaign starts, but delivery data lags by a day, so spend is 0.        |
| **2025-07-02** | `get_media_buy_delivery`             | The first day of delivery data is now available.                        |
| **2025-07-08** | `update_media_buy_performance_index` | The client provides performance feedback to the server.                 |
| **2025-07-10** | `update_media_buy`                   | The client requests a budget reallocation based on performance.         |
| **2025-07-12** | `get_media_buy_delivery`             | Delivery is checked again to see the impact of the budget shift.        |

## How to Run

1.  Ensure all dependencies are installed:
    ```bash
    uv pip install -r pyproject.toml
    ```

2.  Run the simulation script from the project root directory:
    ```bash
    python simulation.py
    ```
