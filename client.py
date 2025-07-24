import asyncio
import argparse
import json
from typing import Dict, Any

import google.generativeai as genai
from fastmcp.client import Client
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

# --- Configuration ---
console = Console()
# IMPORTANT: In a real application, load the API key from a secure source
genai.configure(api_key="AIzaSyBgMWI7SpBfuClTz32wZ-mZg-dPBA9Dbgc")
model = genai.GenerativeModel('gemini-2.5-flash')

# --- Helper Functions ---

def get_model_response(prompt: str) -> Dict[str, Any]:
    """Gets a structured JSON response from the Gemini model."""
    try:
        response = model.generate_content(prompt)
        # A common failure mode is the model wrapping the JSON in ```json ... ```
        clean_json_str = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json_str)
    except (Exception, json.JSONDecodeError) as e:
        console.print(f"[bold red]Error parsing model response: {e}[/bold red]")
        return {}

async def negotiate_proposal(client: Client, brief: str, proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Uses an AI to analyze a proposal and negotiate changes."""
    console.print("\n[bold yellow]AI is reviewing the proposal...[/bold yellow]")
    
    prompt = f"""
    You are an expert media buyer. Your goal is to get the best possible media plan for your client.
    Review the following campaign brief and the publisher's proposal.

    **Original Brief:**
    {brief}

    **Publisher's Proposal:**
    {json.dumps(proposal, indent=2)}

    **Your Task:**
    1.  Analyze if the proposal's packages align well with the brief's objectives and audience.
    2.  Check if the CPMs are reasonable for the audiences and placements offered.
    3.  If the proposal is good, respond with an empty JSON object: {{}}.
    4.  If the proposal could be improved, suggest specific changes. Your response MUST be a JSON object with a "requested_changes" key. This key should contain a list of dictionaries, where each dictionary has "package_id", "field", and "notes".
        -   For "field", you can suggest changes to "cpm", "budget", or "delivery_restrictions".
        -   In "notes", clearly explain WHY you are requesting the change.

    **Example of a good change request:**
    {{
      "requested_changes": [
        {{
          "package_id": "pkg_1_catlovers",
          "field": "cpm",
          "notes": "This CPM is a bit high for a general cat-loving audience. Can we reduce it by 10% to improve efficiency?"
        }}
      ]
    }}

    Return only the JSON object.
    """
    
    ai_review = get_model_response(prompt)
    
    if ai_review and ai_review.get("requested_changes"):
        console.print("[magenta]AI has suggested changes. Sending request back to server...[/magenta]")
        try:
            negotiated_proposal = await client.call_tool(
                "get_proposal",
                {
                    "brief": brief,
                    "proposal_id": proposal["proposal_id"],
                    "requested_changes": ai_review["requested_changes"],
                },
            )
            console.print(Panel("[bold green]Negotiated Proposal Received![/bold green]", expand=False))
            return negotiated_proposal
        except Exception as e:
            console.print(Panel(f"[bold red]An error occurred during negotiation:[/bold red]\n{e}", expand=False))
            return proposal # Return original proposal if negotiation fails
    else:
        console.print("[green]AI finds the proposal acceptable. No changes requested.[/green]")
        return proposal

# --- Main Execution ---

async def main(brief_path: str):
    """A client to negotiate media buys with an ADCP server."""
    
    with open(brief_path, 'r') as f:
        brief_data = json.load(f)
    
    brief = brief_data.get("brief")
    provided_signals = brief_data.get("provided_signals")

    server_script = "main.py"
    console.print(f"Connecting to server via local script: [bold cyan]{server_script}[/]...")
    
    try:
        async with Client(server_script) as client:
            console.print("[bold green]Connection successful![/bold green]")
            
            console.print(f"\n[magenta]Sending brief to server:[/] [italic]{brief}[/italic]")
            try:
                # 1. Get initial proposal
                initial_proposal = await client.call_tool(
                    "get_proposal", 
                    {"brief": brief, "provided_signals": provided_signals}
                )
                
                console.print(Panel("[bold green]Initial Proposal Received![/bold green]", expand=False))
                console.print(Pretty(initial_proposal.structured_content))

                # 2. Negotiate if possible
                if initial_proposal.structured_content.get("media_packages"):
                    final_proposal = await negotiate_proposal(client, brief, initial_proposal.structured_content)
                    console.print(Pretty(final_proposal.structured_content))
                else:
                    console.print("[yellow]No media packages in proposal, nothing to negotiate.[/yellow]")


            except Exception as e:
                console.print(Panel(f"[bold red]An error occurred during tool call:[/bold red]\n{e}", expand=False))

    except Exception as e:
        console.print(f"[bold red]Failed to connect or communicate with the server:[/bold red] {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ADCP Client for testing media buys.")
    parser.add_argument("brief_path", type=str, help="The path to the JSON file containing the campaign brief.")
    args = parser.parse_args()
    
    asyncio.run(main(args.brief_path))
