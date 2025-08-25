# A2A Protocol CLI Alternatives

You're absolutely right - there ARE other CLI options besides the buggy `a2a-cli`! Here's a comprehensive list:

## 1. ✅ **curl** (Most Reliable Native Client)
Already installed on every system. Works perfectly:

```bash
# Send task
curl -X POST https://adcp-sales-agent.fly.dev/a2a/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tasks/send","params":{"message":{"role":"user","parts":[{"text":"get products"}]}},"id":"1"}' | jq .

# Get task result
curl -X POST https://adcp-sales-agent.fly.dev/a2a/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tasks/get","params":{"id":"TASK_ID"},"id":"2"}' | jq .
```

## 2. 🎨 **HTTPie** (Human-Friendly HTTP Client)
Beautiful colored output, intuitive syntax:

```bash
# Install
pip install httpie
# or
brew install httpie  # macOS

# Use
http POST https://adcp-sales-agent.fly.dev/a2a/rpc \
  Content-Type:application/json \
  jsonrpc=2.0 \
  method=tasks/send \
  params:='{"message":{"role":"user","parts":[{"text":"get products"}]}}' \
  id=test-001

# Or with piped JSON
echo '{"jsonrpc":"2.0","method":"tasks/send","params":{"message":{"role":"user","parts":[{"text":"get products"}]}},"id":"1"}' | \
  http POST https://adcp-sales-agent.fly.dev/a2a/rpc Content-Type:application/json
```

## 3. 🍰 **JSONRPCake** (HTTPie Fork for JSON-RPC)
Specifically designed for JSON-RPC:

```bash
# Install
pip install jsonrpcake

# Use (simplified syntax)
jsonrpc adcp-sales-agent.fly.dev:443/a2a/rpc tasks/send \
  message:='{"role":"user","parts":[{"text":"get products"}]}'
```

GitHub: https://github.com/joehillen/jsonrpcake

## 4. 🔧 **jsonrpc-cli** (Dedicated JSON-RPC Tool)
Simple, focused JSON-RPC client:

```bash
# Install
npm install -g jsonrpc-cli
# or
pip install jsonrpc-cli

# Use
jsonrpc-cli --host adcp-sales-agent.fly.dev --port 443 --ssl \
  --path /a2a/rpc tasks/send \
  '{"message":{"role":"user","parts":[{"text":"get products"}]}}'
```

GitHub: https://github.com/dan-da/jsonrpc-cli

## 5. 🐍 **Python with httpx/requests**
Simple Python scripts as CLI:

```python
#!/usr/bin/env python3
import httpx
import json
import sys

def a2a_send(message):
    response = httpx.post(
        "https://adcp-sales-agent.fly.dev/a2a/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"text": message}]
                }
            },
            "id": "py-001"
        }
    )
    return response.json()

if __name__ == "__main__":
    result = a2a_send(sys.argv[1] if len(sys.argv) > 1 else "get products")
    print(json.dumps(result, indent=2))
```

Save as `a2a.py` and use: `python a2a.py "get products"`

## 6. 🎭 **Postman** (GUI Option)
Not CLI, but excellent for testing:

1. Create new request
2. POST to `https://adcp-sales-agent.fly.dev/a2a/rpc`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON):
```json
{
  "jsonrpc": "2.0",
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"text": "get products"}]
    }
  },
  "id": "postman-001"
}
```

## 7. 🐍 **python-a2a** (Full-Featured A2A Library with CLI)
Comprehensive A2A library with built-in CLI (860 stars on GitHub):

```bash
# Install
pip install python-a2a

# Commands available:
a2a send <server> <message>      # Send a message
a2a stream <server> <message>    # Stream responses
a2a serve                        # Start basic server
a2a ui                          # Launch Agent Flow UI
a2a openai                      # OpenAI-powered server
a2a anthropic                   # Anthropic-powered server
a2a mcp-serve                   # MCP server
a2a mcp-agent                   # MCP-enabled agent
a2a workflow run workflow.yaml   # Run workflows
a2a network start network.yaml  # Agent networks
```

⚠️ **Compatibility Note**: The python-a2a CLI expects different endpoint patterns (`/tasks/send`) than the standard A2A protocol (`/rpc`), making it incompatible with our server without modifications.

GitHub: https://github.com/themanojdesai/python-a2a

## 8. 🚀 **FastA2A** (Pydantic's A2A Library)
Turn any agent into a CLI chat app:

```bash
# Install
pip install fasta2a

# Use with Pydantic AI agents
# Provides built-in CLI chat capabilities
```

GitHub: https://github.com/pydantic/fasta2a

## 9. 🔨 **Custom Bash Function**
Add to your `.bashrc` or `.zshrc`:

```bash
a2a() {
  local message="${1:-get products}"
  curl -s -X POST https://adcp-sales-agent.fly.dev/a2a/rpc \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"tasks/send\",\"params\":{\"message\":{\"role\":\"user\",\"parts\":[{\"text\":\"$message\"}]}},\"id\":\"bash-$$\"}" | jq .
}

# Usage
a2a "show me video products"
```

## 10. 🛠️ **jq with curl** (Power User)
For complex interactions:

```bash
# Create task and get ID in one line
TASK_ID=$(curl -s -X POST https://adcp-sales-agent.fly.dev/a2a/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tasks/send","params":{"message":{"role":"user","parts":[{"text":"get products"}]}},"id":"1"}' | \
  jq -r '.result.id')

# Get result
curl -s -X POST https://adcp-sales-agent.fly.dev/a2a/rpc \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tasks/get\",\"params\":{\"id\":\"$TASK_ID\"},\"id\":\"2\"}" | \
  jq -r '.result.artifacts[0].parts[0].text' | jq .
```

## Comparison Table

| Tool | Install | Pros | Cons | Best For |
|------|---------|------|------|----------|
| **curl** | Pre-installed | Universal, reliable | Verbose syntax | Quick tests |
| **HTTPie** | pip/brew | Beautiful output, intuitive | Extra install | Interactive use |
| **JSONRPCake** | pip | JSON-RPC specific | Less maintained | JSON-RPC focus |
| **jsonrpc-cli** | npm/pip | Dedicated tool | Requires Node/Python | JSON-RPC only |
| **Python script** | python | Customizable | Need to write | Automation |
| **Postman** | Download app | GUI, collections | Not CLI | Complex testing |
| **python-a2a** | pip | Full suite, many features | Incompatible endpoints | Own A2A servers |
| **FastA2A** | pip | Full A2A support | Python only | Pydantic agents |
| **Bash function** | None | Quick access | Basic only | Daily use |

## The a2a-cli Bug

The original `a2a-cli` has a bug where it ignores the `--server` flag and defaults to `localhost:8000`. Until fixed, use any of the alternatives above!

## Recommendation

For most users, I recommend:
1. **curl** for quick tests (already installed)
2. **HTTPie** for better UX (if you can install it)
3. **Custom Python/Bash script** for daily use

All of these work perfectly with our deployed A2A server!
