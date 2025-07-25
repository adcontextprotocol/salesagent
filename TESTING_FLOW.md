# V2.3 Testing & Simulation Flow

This document explains how to run the end-to-end simulation of the V2.3 media buying lifecycle.

The simulation is orchestrated by the `simulation.py` script, which acts as the client (the "Orchestrator"). It communicates with the server (`main.py`) in local script mode, stepping through a dynamic, three-phase lifecycle.

## How it Works

The simulation demonstrates the core capabilities of the V2.3 API in a single, continuous flow. Unlike previous versions that used a fixed timeline, the V2.3 simulation is dynamic, with each step building on the output of the last. The `mock_ad_server.py` is used to simulate the passage of time for campaign reporting.

## The Simulation Lifecycle

The `simulation.py` script executes the following sequence of events, printing the result of each step:

| Phase         | Action                               | Purpose                                                                 |
|---------------|--------------------------------------|-------------------------------------------------------------------------|
| **1. Discover** | `list_products`                      | The client sends a natural language brief from `brief.json`. The server uses an LLM to analyze the brief and recommend products from its catalog. |
| **2. Buy**      | `create_media_buy`                   | The client uses the AI's recommendations to construct and send a `CreateMediaBuyRequest`, including a budget, flight dates, and a targeting overlay. |
| **3. Simulate** | `check_media_buy_status` & `MockAdServer` | The client simulates a 90-day campaign flight, printing a weekly report showing server status and delivery metrics (spend, impressions, pacing) from the mock ad server. |

## How to Run

1.  Ensure all dependencies are installed and `config.json` is configured with your Gemini API key (see `README.md`).

2.  Run the simulation script from the project root directory:
    ```bash
    python3 simulation.py
    ```