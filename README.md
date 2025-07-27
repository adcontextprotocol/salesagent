# AdCP Buy-Side Server (V2.3)

This project is a Python-based reference implementation of an Advertising Context Protocol (AdCP) V2.3 buy-side server. It demonstrates how a publisher can expose its advertising inventory to an AI-driven client.

The server can:
-   Receive a natural language brief describing campaign goals.
-   Use a Large Language Model (Gemini 1.5 Flash) to recommend suitable advertising products.
-   Accept a media buy request to purchase those products.
-   Simulate the entire 90-day lifecycle of the campaign.

## How to Run the Simulation

This project is designed to be run as a self-contained, end-to-end simulation that showcases the entire media buying lifecycle.

1.  **Prerequisites:**
    -   Python 3.10+
    -   `uv` (or `pip`) for package installation.

2.  **Installation:**
    ```bash
    uv pip install -r requirements.txt
    ```

3.  **Configuration:**
    -   Copy `config.json.sample` to `config.json`.
    -   Add your Gemini API key to `config.json`.
    ```json
    {
      "gemini_api_key": "YOUR_API_KEY_HERE"
    }
    ```

4.  **Run the Simulation:**
    Execute the simulation script from the project root directory. This will start the server, run the client, and print a step-by-step log of the entire process.
    ```bash
    python3 simulation.py
    ```

## Core V2.3 Architecture

-   **`main.py` (Server):** A `FastMCP` server that exposes the AdCP tools (`list_products`, `create_media_buy`).
-   **`simulation.py` (Client):** An orchestrator that calls the server's tools in sequence to simulate a real-world buying process.
-   **`schemas.py`:** Contains all the Pydantic models that define the V2.3 API data contracts (e.g., `Product`, `Targeting`, `CreateMediaBuyRequest`).
-   **`database.py`:** Initializes a simple SQLite database with a catalog of advertising `products`.
-   **`adapters/`:** Directory containing adapter implementations for various ad servers (mock, GAM, Kevel, Triton).
-   **`test_main.py`:** A unit test that validates the AI's output against the Pydantic schemas, ensuring structural correctness.
