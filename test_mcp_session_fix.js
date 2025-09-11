#!/usr/bin/env node

const { Client } = require('modelcontextprotocol/sdk/client/index.js');
const { StreamableHTTPClientTransport } = require('modelcontextprotocol/sdk/client/streamableHttp.js');

async function testMCPConnection() {
  console.log('Testing MCP connection and session handling...');

  const client = new Client({
    name: 'test-client',
    version: '1.0.0'
  });

  const transport = new StreamableHTTPClientTransport(
    new URL('http://localhost:8080/mcp/'),
    {
      requestInit: {
        headers: {
          'x-adcp-auth': process.env.TEST_ADCP_TOKEN || 'your-test-token-here'
        }
      }
    }
  );

  try {
    console.log('1. Connecting to transport...');
    await client.connect(transport);
    console.log('✓ Transport connected');

    console.log('2. Testing tool call...');
    const result = await client.request({
      method: 'tools/call',
      params: {
        name: 'get_products',
        arguments: {
          brief: 'Premium coffee brand',
          promoted_offering: 'Organic coffee beans'
        }
      }
    });

    console.log('✓ Tool call successful');
    console.log('Result:', JSON.stringify(result, null, 2));

  } catch (error) {
    console.error('❌ Error:', error.message);

    // More detailed error analysis
    if (error.message.includes('Missing session ID')) {
      console.error('Session ID issue - server needs session configuration');
    } else if (error.message.includes('authentication')) {
      console.error('Authentication issue - check x-adcp-auth header');
    } else {
      console.error('Full error details:', error);
    }
  } finally {
    console.log('3. Closing connection...');
    await client.close();
    console.log('✓ Connection closed');
  }
}

// Run the test
testMCPConnection().catch(console.error);
