/**
 * Load official MCP SDK components for browser use
 * This module loads the official @modelcontextprotocol/sdk for proper MCP protocol compliance
 */

// Load official MCP SDK asynchronously and expose factory function
(async function() {
    try {
        console.log('Loading official MCP SDK...');

        // Import official MCP client components
        const { Client } = await import('https://unpkg.com/@modelcontextprotocol/sdk@latest/dist/esm/client/index.js');
        const { StreamableHttpTransport } = await import('https://unpkg.com/@modelcontextprotocol/sdk@latest/dist/esm/client/streamableHttp.js');

        console.log('✅ Official MCP SDK loaded successfully');

        // Expose factory function globally
        window.createMCPClient = function(options) {
            console.log('Creating official MCP client');

            const transport = new StreamableHttpTransport({
                url: options.url,
                headers: options.headers
            });

            return new Client(transport);
        };

        // Signal that MCP client is ready
        window.mcpClientReady = true;

        // Dispatch event for any waiting code
        if (typeof CustomEvent !== 'undefined') {
            window.dispatchEvent(new CustomEvent('mcpClientReady'));
        }

    } catch (error) {
        console.error('❌ Failed to load official MCP SDK:', error);

        // Provide clear error information
        const errorDetails = error.message || error.toString();
        console.error('Error details:', errorDetails);

        // Signal that MCP client failed to load
        window.mcpClientError = errorDetails;

        // Dispatch error event
        if (typeof CustomEvent !== 'undefined') {
            window.dispatchEvent(new CustomEvent('mcpClientError', { detail: errorDetails }));
        }
    }
})();
