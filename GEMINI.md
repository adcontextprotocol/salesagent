# Gemini Agent Notes

## Project Overview

This project is a Python-based implementation of the Advertising Context Protocol (AdCP) V2.3 for the buy-side. It acts as a server that can receive a natural language brief from a client, recommend advertising products using a large language model (Gemini 1.5 Flash), and then simulate the entire lifecycle of a media buy based on those recommendations.

## Core Architecture (V2.3)

The project was refactored to a simpler, more powerful V2.3 specification.

1.  **`main.py` (The Server):** The core of the application. It uses the `fastmcp` library to expose a set of V2.3 tools. The primary tool is `list_products`, which takes a natural language brief and uses an LLM to select suitable products from a catalog. It maintains the state of media buys in-memory.

2.  **`schemas.py` (The Data Contracts):** This file contains the Pydantic models for the V2.3 API. Key models include `Product`, `Targeting`, `Format`, `ListProductsRequest`, and `CreateMediaBuyRequest`. These schemas are the blueprint for the entire system.

3.  **`database.py` (The Inventory):** This script initializes a simple SQLite database containing a single `products` table. Each row represents a `Product`, with complex objects like `formats` and `targeting_template` stored as JSON. This simplified structure was a major outcome of the V2.3 refactoring.

4.  **`mock_ad_server.py` (The Simulation Engine):** This simulates campaign delivery. It's initialized with a `CreateMediaBuyRequest` and calculates delivery metrics (spend, impressions, pacing) for a given simulated date.

5.  **`simulation.py` (The Client/Orchestrator):** This script drives the end-to-end testing flow for V2.3. It reads a natural language `brief.json`, calls `list_products` to get AI recommendations, creates a media buy, and then simulates a 90-day campaign flight, printing weekly progress reports.

## Development & Testing Strategy (V2.3)

The non-deterministic nature of the AI model required a specific testing strategy.

1.  **Schema Validation Testing (`test_main.py`):** The most important test asserts that the output of the AI-driven `list_products` tool successfully validates against the strict `ListProductsResponse` Pydantic model. This ensures that no matter what the AI chooses, the server's response is always structurally correct. The test also verifies that the AI only returns products that exist in the database.

2.  **Simulation-Based Testing (`simulation.py`):** The simulation script is our primary tool for integration and end-to-end testing. By running the full lifecycle (Discover -> Buy -> Simulate), we can verify that the state is managed correctly and that the different tools and data models work together as expected. The clear, step-by-step output allows for easy manual verification of the AI's logic and the simulation's correctness.