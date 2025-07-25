# ADCP Buy-Side Server

This project is a Python-based reference implementation of an Agentic Digital Content Protocol (ADCP) buy-side server. It uses a mock ad server and an AI media planner (powered by Gemini 2.5 Flash) to simulate the entire lifecycle of a media buy, from negotiation to final reporting.

The primary entry point for testing and demonstration is the `simulation.py` script, which orchestrates a complete, multi-step campaign flow.

## Getting Started

### 1. Installation

This project uses `uv` for package management. First, ensure `uv` is installed:
```bash
pip install uv
```

Then, install the project dependencies from the root directory:
```bash
uv pip install -r pyproject.toml
```

### 2. Configuration

The server uses the Google Gemini API. You must have an API key for the service. The key is currently hardcoded in `main.py`. Please replace the placeholder with your actual key.

**IMPORTANT:** In a production environment, this key should be stored securely (e.g., as an environment variable or in a secret manager).

## How to Run the Simulation

The primary way to interact with this project is through the end-to-end simulation script. This script acts as the client and runs through a complete media buying lifecycle, from proposal to reporting, using a mock `brief.json` file.

To run the simulation, execute the following command from the project root:
```bash
python simulation.py
```
The script will print the actions it's taking and the results from the server at each step of the simulated timeline. For a detailed explanation of the simulation flow, please see `TESTING_FLOW.md`.

## How to Run the Tests

The project includes a test suite that validates the core functionality. The most important test ensures that the AI-generated proposals conform to the required Pydantic data schemas.

To run the tests, execute the following command from the project root:
```bash
python -m unittest test_main.py
```
