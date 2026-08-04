import type { Express, Request, Response } from 'express'
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js'
import config from '../config.js'
import { buildMcpServer } from './server.js'

/**
 * Mounts the MCP server at /mcp using the Streamable HTTP transport in
 * stateless mode: each POST gets a fresh server + transport, so requests are
 * fully isolated and no session state is held. GET (SSE notifications) and
 * DELETE (session teardown) don't apply in stateless mode and return 405.
 */

function unauthorized(res: Response): void {
  res.status(401).json({
    jsonrpc: '2.0',
    error: { code: -32001, message: 'Missing or invalid bearer token' },
    id: null
  })
}

function methodNotAllowed(res: Response): void {
  res.status(405).json({
    jsonrpc: '2.0',
    error: { code: -32000, message: 'Method not allowed: this MCP server is stateless' },
    id: null
  })
}

export function mountMcp(app: Express): void {
  app.post('/mcp', async (req: Request, res: Response) => {
    if (config.token && req.headers.authorization !== `Bearer ${config.token}`) {
      unauthorized(res)
      return
    }
    const server = buildMcpServer()
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined })
    res.on('close', () => {
      transport.close()
      server.close()
    })
    try {
      await server.connect(transport)
      await transport.handleRequest(req, res, req.body)
    } catch (error) {
      console.error('MCP request failed:', error)
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: '2.0',
          error: { code: -32603, message: 'Internal server error' },
          id: null
        })
      }
    }
  })

  app.get('/mcp', (_req, res) => methodNotAllowed(res))
  app.delete('/mcp', (_req, res) => methodNotAllowed(res))
}
