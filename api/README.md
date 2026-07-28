# archive-wiki-api

HTTP API over this Archive Wiki, so LLM engines (and, later, MCP clients) can
query the archive without a local checkout — and file conversations back into
it for curation. The same five functions are exposed twice: as REST under
`/v1/*` and as an **MCP server** (Streamable HTTP at `/mcp`, plus a stdio
entry point). PRD: `llm_engine` `docs/pages/developers/archive_wiki_api.md`.
Milestones **M1** (read surface), **M2** (push-back), and **M3** (MCP) are
implemented.

## Run

Requires **Node 20+**. The API is a stateless view over the wiki checkout it
lives in — it reads markdown from disk and writes only to `inbox/conversations/`.

### Development

```bash
cd api
npm install
npm run dev          # tsx watch, http://localhost:4000
curl localhost:4000/v1/health
```

### Production

```bash
cd api
npm ci
npm run build        # tsc → dist/
npm start            # node dist/index.js
```

Create `api/.env` from `api/.env.example` first (the process loads it via
`dotenv`), or set the same variables in the environment:

| Variable | Default | Notes |
| --- | --- | --- |
| `PORT` | `4000` | Port the HTTP server binds. |
| `ARCHIVE_PATH` | the wiki repo root (this package's parent) | Absolute path to the archive-wiki checkout to serve. Leave unset when the API runs from inside the checkout. |
| `ARCHIVE_API_TOKEN` | *(unset)* | Shared bearer token. When set, every route except `GET /v1/health` requires `Authorization: Bearer <token>`. **Unset means no auth — always set it in production.** |

Operational notes:

- **The search index is built once at startup**, in memory. After the wiki
  content changes (a `git pull`, a `scripts/build.mjs` run), either restart the
  process or `curl -X POST localhost:4000/v1/reindex` to pick the changes up.
  This is not a rare event — see "Keeping content fresh" below.
- **`GET /v1/health`** is unauthenticated and returns index stats — use it as
  the process manager / load balancer health check.
- The process needs **write permission on `inbox/conversations/`**; that is the
  only path it writes to.
- Run it behind TLS if the engine reaches it over anything but localhost — the
  bearer token is the only credential.

A minimal systemd unit:

```ini
[Unit]
Description=archive-wiki-api
After=network.target

[Service]
WorkingDirectory=/srv/archive-wiki/api
EnvironmentFile=/srv/archive-wiki/api/.env
ExecStart=/usr/bin/node dist/index.js
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Keeping content fresh

The wiki is **not static** — three GitHub Actions commit new items to `main`
every day (`fetch-youtube-captions.yml` 06:17, `fetch-tagteam-items.yml` 06:47,
`fetch-publications.yml` 07:05, all UTC), and `synthesize-wiki.yml` adds pages
when enabled. A long-running deployment therefore serves a **stale search
index** within a day of starting unless it pulls and reindexes. Direct page and
item reads come off disk per request and stay correct; it's search that drifts.

Pull after the last daily job, then reindex in place — no restart, no dropped
requests:

```cron
# user crontab. One line — cron has no line continuation. Note the schedules
# above are UTC (GitHub Actions); cron here runs in the server's timezone.
ARCHIVE_API_TOKEN=<same token as the service>
30 7 * * * cd /srv/archive-wiki && git pull --ff-only && curl -fsS -X POST -H "Authorization: Bearer $ARCHIVE_API_TOKEN" localhost:4000/v1/reindex
```

> **Do not `git clean -fd` or `git reset --hard` in a deploy script.** The API
> writes conversation drafts into `inbox/conversations/` in this same checkout,
> and they are untracked until a curator commits them — a clean would delete
> unreviewed drafts. `git pull --ff-only` is safe: nothing upstream creates
> those paths.

Confirm a reindex took effect with the `builtAt` timestamp:

```bash
curl -s localhost:4000/v1/health   # {"index":{"pages":…,"items":…,"builtAt":…}}
```

### Connecting llm_engine

Point the engine at this service by setting, in the **llm_engine** `.env`:

```bash
ARCHIVE_API_URL=http://<host>:4000
ARCHIVE_API_TOKEN=<same token as above>
```

`ARCHIVE_API_URL` takes precedence over the engine's legacy `ARCHIVE_PATH`
filesystem mode, and the mode is chosen once at startup — if this API is down
the engine does **not** fall back to reading a local checkout. See llm_engine
`docs/pages/developers/archive_wiki_api.md` §6.

## Endpoints (v1, JSON)

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/search?q=&section=&limit=` | Lexical search over wiki pages + item stubs; ranked `{section, slug, title, snippet, score, id?}` |
| `GET /v1/pages?section=` | List curated wiki pages (topics, people, orgs, events, timeline) |
| `GET /v1/pages/:slug` · `GET /v1/pages/:section/:slug` | Read one page: frontmatter + markdown (8k-char cap) |
| `GET /v1/items/:id` | Archive item stub + full source (YouTube transcript for `yt_*` ids, article/newsletter text otherwise; 12k-char cap) |
| `POST /v1/conversations` | File a conversation as a draft in `inbox/conversations/` for curator review. Body: `{title, markdown, date?, source?, participants?, topic?}` → `201 {slug, path}` |
| `GET /v1/health` | Liveness + index stats |
| `POST /v1/reindex` | Rebuild the search index after content changes |

The search index is in-memory, built at startup. The `/v1/search` contract is
retrieval-agnostic — the lexical backend can be swapped for vectors later
without changing clients.

## Examples

```bash
curl 'localhost:4000/v1/search?q=content+moderation&limit=5'
curl 'localhost:4000/v1/pages?section=topics'
curl 'localhost:4000/v1/pages/topics/ai-governance-and-regulation'
curl 'localhost:4000/v1/items/yt_BSt010su3rU'
curl -X POST 'localhost:4000/v1/conversations' -H 'Content-Type: application/json' \
  -d '{"title": "Historian Q&A on content moderation", "source": "slack", "topic": "content-moderation-and-speech", "markdown": "**Q:** ...\n\n**A:** ..."}'
```

Filed drafts are **not** wiki pages: `inbox/` (like `api/` itself) is stripped
from the published Quartz site by the deploy workflow, and drafts stay out of
the search index. A curator promotes or discards them — see the wiki's
`AGENTS.md` §5 "Review the inbox".

## MCP server

Five tools, 1:1 with the REST surface and named what the llm_engine historian
already knows: `search_archive`, `list_archive_wiki_pages`,
`read_archive_wiki_page`, `get_archive_item`, `save_conversation_to_archive`.

- **Streamable HTTP** — mounted at `POST /mcp` on the same server, stateless
  (fresh server per request; GET/DELETE return 405). Auth: same bearer token
  via the `Authorization` header when `ARCHIVE_API_TOKEN` is set.
- **stdio** — for local clients (Claude Desktop, Claude Code):
  `npm run build && npm run mcp:stdio` (or `npm run mcp:stdio:dev`). Example
  client config:

  ```json
  {
    "mcpServers": {
      "archive-wiki": {
        "command": "node",
        "args": ["/path/to/archive-wiki/api/dist/mcp/stdio.js"]
      }
    }
  }
  ```

Verify interactively with `npx @modelcontextprotocol/inspector` pointed at
`http://localhost:4000/mcp` (Streamable HTTP) or at the stdio command.
