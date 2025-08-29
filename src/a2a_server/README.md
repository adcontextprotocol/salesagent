# A2A Smart Client

A protocol-aware client for A2A (Agent-to-Agent) Protocol servers that understands sessions, task lifecycle, and provides rich interactive features.

## Features

- **Protocol-Aware**: Understands A2A protocol semantics including Agent Cards, skills, and task states
- **Session Management**: Maintains context_id for conversation continuity across multiple interactions
- **Task Lifecycle**: Handles task creation, polling, and completion with progress indicators
- **Interactive Chat**: Persistent chat mode with session context
- **Rich CLI**: Beautiful terminal output with syntax highlighting and progress spinners
- **Error Handling**: Robust error handling with helpful error messages

## Installation

The smart client is already included in the project dependencies:

```bash
uv run python src/a2a_server/smart_client.py --help
```

## Usage

### Discovery - Get Agent Information

```bash
# Local server
uv run python src/a2a_server/smart_client.py info

# Production server
uv run python src/a2a_server/smart_client.py info --server https://adcp-sales-agent.fly.dev/a2a
```

### Send Tasks

```bash
# Simple query
uv run python src/a2a_server/smart_client.py send "What products are available?"

# Query with specific skill
uv run python src/a2a_server/smart_client.py send "Create a campaign with $5000 budget" --skill create_campaign

# Don't wait for completion
uv run python src/a2a_server/smart_client.py send "Long running task" --no-wait
```

### Interactive Chat Mode

```bash
# Start interactive chat with persistent context
uv run python src/a2a_server/smart_client.py chat

# Chat with production server
uv run python src/a2a_server/smart_client.py chat --server https://adcp-sales-agent.fly.dev/a2a

# Use custom context ID for session continuity
uv run python src/a2a_server/smart_client.py chat --context "my-session-123"
```

### Get Task Status

```bash
# Get specific task by ID
uv run python src/a2a_server/smart_client.py task <task-id>
```

### Run Test Suite

```bash
# Test local server
uv run python src/a2a_server/smart_client.py test

# Test production server
uv run python src/a2a_server/smart_client.py test --server https://adcp-sales-agent.fly.dev/a2a
```

## Protocol Features

### Session Management

The client maintains session state across interactions:
- **session_id**: Unique identifier for the client session
- **context_id**: Conversation thread identifier for maintaining context
- Persistent context in chat mode for multi-turn conversations

### Task Lifecycle

The client handles the complete task lifecycle:
1. **Submit**: Send task via `tasks/send` RPC method
2. **Poll**: Automatically poll `tasks/get` for status updates
3. **Complete**: Return final result when task completes
4. **Progress**: Show visual progress indicators during polling

### Agent Discovery

Automatically fetches and parses Agent Cards to:
- Discover available skills and capabilities
- Get correct RPC endpoint URLs
- Display agent metadata and descriptions

## Key Advantages Over Basic Clients

Unlike simple HTTP clients or the basic a2a-cli, this smart client:

1. **Understands the Protocol**: Knows about task states, Agent Cards, and RPC methods
2. **Manages Sessions**: Maintains context across multiple interactions
3. **Handles Async Operations**: Automatically polls for task completion with progress indicators
4. **Rich User Experience**: Beautiful terminal UI with colors, tables, and progress spinners
5. **Error Recovery**: Handles network errors, timeouts, and protocol errors gracefully
6. **Interactive Mode**: Chat interface with persistent context for natural conversations

## Examples

### Example 1: Product Discovery

```bash
$ uv run python src/a2a_server/smart_client.py send "Show me video advertising products"

Sending: Show me video advertising products
✓ Processing task 5b96dc19...

Result:
{
  "products": [
    {
      "id": "prod_sports_video",
      "name": "Sports Video Inventory",
      "description": "Premium video advertising slots in sports content",
      "formats": ["video_16x9", "video_vertical"],
      "pricing": {
        "cpm": 25.0,
        "minimum_budget": 5000
      }
    }
  ]
}
```

### Example 2: Interactive Chat

```bash
$ uv run python src/a2a_server/smart_client.py chat

╭─────────────────────────────── A2A Smart Chat ───────────────────────────────╮
│ Connected to: http://localhost:8091                                          │
│ Context ID: chat-378f3fc0                                                    │
│ Session ID: ac74ff31-4872-47c5-a30d-e8f58dc615da                            │
│ Type 'exit' or 'quit' to end the chat                                        │
│ Type '/skills' to list available skills                                      │
╰──────────────────────────────────────────────────────────────────────────────╯

You: What products do you have?

Agent:
Found 2 products:
  • Sports Video Inventory: Premium video advertising slots in sports content
    CPM: $25.0
  • Sports Display Ads: Display advertising across sports sections
    CPM: $10.0

You: Create a campaign for the video product with $10000

Agent:
Campaign created successfully!
  Campaign ID: camp_12345
  Status: Active
  Budget: $10,000
  Product: Sports Video Inventory
```

## Architecture

The smart client is built with:
- **httpx**: Async HTTP client for network requests
- **typer**: Modern CLI framework for command parsing
- **rich**: Beautiful terminal formatting and progress indicators
- **asyncio**: Async/await for efficient network operations
- **Pydantic-compatible**: Works with official a2a-sdk types

## Testing

The client includes a comprehensive test suite that validates:
- Agent discovery
- Product browsing
- Campaign creation
- Creative management
- Report generation

Run the test suite to verify server compatibility:

```bash
uv run python src/a2a_server/smart_client.py test --server <your-server-url>
```
