import express from 'express'
import type { Request, Response, NextFunction } from 'express'
import config from './config.js'
import v1Router from './routes/v1.js'
import { mountMcp } from './mcp/http.js'

const app = express()

app.use(express.json({ limit: '2mb' }))

// MCP (Streamable HTTP) — does its own auth so it can return JSON-RPC errors.
mountMcp(app)

// Shared-token auth: everything except /v1/health requires the bearer token
// when ARCHIVE_API_TOKEN is set. Open when unset (local development).
app.use('/v1', (req: Request, res: Response, next: NextFunction) => {
  if (!config.token || req.path === '/health') {
    next()
    return
  }
  if (req.headers.authorization === `Bearer ${config.token}`) {
    next()
    return
  }
  res.status(401).json({ error: 'unauthorized', message: 'Missing or invalid bearer token' })
})

app.use('/v1', v1Router)

app.use((req: Request, res: Response) => {
  res.status(404).json({ error: 'not_found', message: `No route ${req.method} ${req.path}` })
})

app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error(err)
  res.status(500).json({ error: 'internal', message: err.message })
})

export default app
