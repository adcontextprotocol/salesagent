# Gemini Agent Notes

## Project Overview

This project is a Python-based implementation of the Agentic Digital Content Protocol (ADCP) for the buy-side. It acts as a server that can receive briefs from a client, generate media proposals using a large language model (Gemini 2.5 Flash), and then simulate the entire lifecycle of a media buy based on that proposal.

## Core Architecture

The project is built around a few key components:

1.  **`main.py` (The Server):** This is the core of the application. It uses the `fastmcp` library to expose a set of tools that conform to the ADCP specification. It maintains the state of proposals and media buys in-memory, making it easy to run and test without external database dependencies.

2.  **`schemas.py` (The Data Contracts):** This file contains all the Pydantic models that define the structure of the data exchanged between the client and server. Creating a shared schema was a crucial refactoring step that eliminated a whole class of data mismatch errors.

3.  **`database.py` (The Inventory):** This script initializes a simple SQLite database that acts as the publisher's inventory catalog. It contains sample data for audiences, properties, and ad placements. The `get_proposal` tool uses this data as the context for the AI to build media plans from.

4.  **`mock_ad_server.py` (The Simulation Engine):** This is the heart of the campaign lifecycle simulation. It takes a media buy's parameters (flight dates, budget, etc.) and a simulated "today" date, and calculates delivery metrics. This allows us to test the entire campaign flow without needing a real ad server or waiting for time to pass.

5.  **`simulation.py` (The Client/Orchestrator):** This script acts as the client and drives the end-to-end testing flow. It reads a `brief.json` file and then programmatically calls the server's tools in a sequence that mimics a real-world media buying process, from negotiation to reporting. It uses the `today` parameter to "fast-forward" time at each step.

## Development & Testing Strategy

A key challenge in this project was the non-deterministic nature of the AI model. We couldn't write traditional unit tests that assert an exact output for the `get_proposal` tool.

Our strategy to overcome this was twofold:

1.  **Schema Validation Testing (`test_main.py`):** The most important test asserts that the output of the AI-driven tools (like `get_proposal`) successfully validates against our strict Pydantic models. This ensures that no matter what the AI chooses, the server's response is always structurally correct and usable by the client.

2.  **Simulation-Based Testing (`simulation.py`):** The simulation script is our primary tool for integration and end-to-end testing. By running the full lifecycle, we can verify that the state is managed correctly and that the different tools work together as expected. The clear, step-by-step output allows for easy manual verification of the AI's logic and the simulation's correctness. This proved invaluable for debugging issues with date handling and data serialization.
