/**
 * Browser-compatible MCP (Model Context Protocol) client
 * This is a dependency-free fallback implementation that works in all browsers
 * without requiring Node.js modules like 'ajv' that can't resolve via unpkg
 */

class BrowserMCPClient {
    constructor(transport) {
        this.transport = transport;
        this.connected = false;
        this.sessionId = null;
    }

    async connect() {
        if (this.connected) return;

        // Initialize session with MCP server
        try {
            const initResponse = await this.transport.request({
                jsonrpc: "2.0",
                id: this.generateId(),
                method: "initialize",
                params: {
                    protocolVersion: "2024-11-05",
                    capabilities: {
                        tools: {}
                    },
                    clientInfo: {
                        name: "browser-mcp-client",
                        version: "1.0.0"
                    }
                }
            });

            if (initResponse.error) {
                throw new Error(`MCP initialization failed: ${initResponse.error.message}`);
            }

            this.connected = true;
            console.log('MCP client connected successfully');
        } catch (error) {
            console.error('MCP connection failed:', error);
            throw error;
        }
    }

    async callTool(toolName, arguments_) {
        if (!this.connected) {
            await this.connect();
        }

        const request = {
            jsonrpc: "2.0",
            id: this.generateId(),
            method: "tools/call",
            params: {
                name: toolName,
                arguments: arguments_ || {}
            }
        };

        try {
            const response = await this.transport.request(request);

            if (response.error) {
                throw new Error(`Tool call failed: ${response.error.message}`);
            }

            return response.result;
        } catch (error) {
            console.error(`MCP tool call '${toolName}' failed:`, error);
            throw error;
        }
    }

    generateId() {
        return `browser-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
}

class BrowserStreamableHttpTransport {
    constructor(options) {
        this.url = options.url;
        this.headers = options.headers || {};
        this.timeout = options.timeout || 30000;
    }

    async request(jsonRpcRequest) {
        const response = await fetch(this.url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                ...this.headers
            },
            body: JSON.stringify(jsonRpcRequest)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const responseText = await response.text();

        // Handle Server-Sent Events (SSE) format
        if (responseText.startsWith('event: message\ndata: ')) {
            const dataLine = responseText.split('\n').find(line => line.startsWith('data: '));
            if (dataLine) {
                return JSON.parse(dataLine.substring(6));
            }
        }

        // Handle regular JSON response
        return JSON.parse(responseText);
    }
}

// Factory function to create MCP client with proper fallback
window.createMCPClient = function(options) {
    console.log('Creating browser-compatible MCP client');

    const transport = new BrowserStreamableHttpTransport({
        url: options.url,
        headers: options.headers
    });

    return new BrowserMCPClient(transport);
};

// Attempt to load official MCP SDK if available, otherwise use fallback
async function initializeOfficialMCP() {
    try {
        // Try to import official MCP SDK
        const { Client } = await import('https://unpkg.com/@modelcontextprotocol/sdk@latest/dist/esm/client/index.js');
        const { StreamableHttpTransport } = await import('https://unpkg.com/@modelcontextprotocol/sdk@latest/dist/esm/client/streamableHttp.js');

        console.log('Official MCP SDK loaded successfully');

        // Override factory with official implementation
        window.createMCPClient = function(options) {
            const transport = new StreamableHttpTransport({
                url: options.url,
                headers: options.headers
            });
            return new Client(transport);
        };

        return true;
    } catch (error) {
        console.log('Official MCP SDK not available, using browser-compatible fallback:', error.message);
        return false;
    }
}

// Initialize on load
if (typeof window !== 'undefined') {
    // Try official SDK first, fall back to browser implementation
    initializeOfficialMCP().catch(() => {
        console.log('Using browser-compatible MCP client fallback');
    });
}
