import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import config from '../config.js'
import { buildIndex } from '../core/search.js'
import { buildMcpServer } from './server.js'

// Stdio entry point for local MCP clients (Claude Desktop, Claude Code, etc.):
//   node dist/mcp/stdio.js   (or: npm run mcp:stdio)
// stdout is the protocol channel — log to stderr only.

const stats = buildIndex(config.archivePath)
console.error(
  `archive-wiki MCP (stdio): index built — ${stats.pages} wiki pages, ${stats.items} item stubs (${config.archivePath})`
)

const server = buildMcpServer()
await server.connect(new StdioServerTransport())
