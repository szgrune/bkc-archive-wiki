import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { z } from 'zod'
import config from '../config.js'
import { WIKI_SECTIONS, listPages, readPage } from '../core/wiki.js'
import { getItem } from '../core/items.js'
import { searchWiki } from '../core/search.js'
import { saveConversation, validateConversation } from '../core/conversations.js'

/**
 * MCP server over the same core functions the REST routes wrap. Five tools,
 * named what the llm_engine historian already knows (search_archive,
 * list_archive_wiki_pages, read_archive_wiki_page, get_archive_item) plus
 * save_conversation_to_archive. Tool descriptions carry the routing guidance
 * (list → read → get) from the historian prompt.
 */

function text(value: string) {
  return { content: [{ type: 'text' as const, text: value }] }
}

export function buildMcpServer(): McpServer {
  const server = new McpServer({ name: 'archive-wiki', version: '0.1.0' })

  server.registerTool(
    'search_archive',
    {
      description:
        'Keyword search across the BKC Archive Wiki: curated topic/people/org/event/timeline pages and ' +
        'the 7,000+ archive item stubs. Use this for content questions about what the archive holds. ' +
        'Results carry a section + slug (open with read_archive_wiki_page) or an item id (open with get_archive_item).',
      inputSchema: {
        query: z.string().describe('The search query, e.g. "content moderation", "Zittrain on AI agents"'),
        section: z
          .enum([...WIKI_SECTIONS, 'items'])
          .optional()
          .describe('Limit results to one section. Omit to search everything.'),
        limit: z.number().int().min(1).max(50).optional().describe('Max results, default 10')
      }
    },
    async ({ query, section, limit }) => {
      const results = searchWiki(query, { section, limit: limit ?? 10 })
      if (results.length === 0) return text('No relevant archive content found.')
      const lines = results.map((r) => {
        const ref = r.id ? `item ${r.id}` : `${r.section}/${r.slug}`
        return `- [${ref}] "${r.title}" (score ${r.score})\n  ${r.snippet}`
      })
      return text(lines.join('\n'))
    }
  )

  server.registerTool(
    'list_archive_wiki_pages',
    {
      description:
        'List the curated archive-wiki pages: thematic topic pages, people, organizations, events, and ' +
        'per-year timeline narratives. Use this first to route a question about a theme, person, org, or era ' +
        'to the right page, then call read_archive_wiki_page with the exact slug.',
      inputSchema: {
        section: z
          .enum([...WIKI_SECTIONS])
          .optional()
          .describe('Limit to one section: topics, people, orgs, events, or timeline. Omit to list all.')
      }
    },
    async ({ section }) => {
      const pages = listPages(config.archivePath, section)
      if (pages.length === 0) return text('No wiki pages found.')
      const lines = pages.map((p) => {
        const extras = [
          p.meta.item_count ? `${p.meta.item_count} items` : null,
          p.meta.related ? `related: ${p.meta.related}` : null,
          p.meta.related_topics ? `topics: ${p.meta.related_topics}` : null,
          p.meta.affiliations ? `affiliations: ${p.meta.affiliations}` : null
        ]
          .filter(Boolean)
          .join(' | ')
        return `- [${p.section}] ${p.slug} — "${p.title}"${extras ? ` (${extras})` : ''}`
      })
      return text(lines.join('\n'))
    }
  )

  server.registerTool(
    'read_archive_wiki_page',
    {
      description:
        'Read one curated archive-wiki page by slug (from list_archive_wiki_pages or search_archive). ' +
        'Pages link to archive items as wiki-links like [[<itemId>-<slug>|Title]] — pass that leading itemId ' +
        '(e.g. "17120704" or "yt_BSt010su3rU") to get_archive_item to retrieve the underlying source material.',
      inputSchema: {
        slug: z.string().describe('The page slug, e.g. "ai-governance-and-regulation" or "jonathan-zittrain"'),
        section: z
          .enum([...WIKI_SECTIONS])
          .optional()
          .describe('Which section the slug is in, if known. Omit to search all sections.')
      }
    },
    async ({ slug, section }) => {
      const page = readPage(config.archivePath, slug, section)
      if (!page) {
        return text(`No wiki page found for slug "${slug}". Use list_archive_wiki_pages to see valid slugs.`)
      }
      return text(page.markdown)
    }
  )

  server.registerTool(
    'get_archive_item',
    {
      description:
        'Retrieve one archive item by id: its stub metadata plus the full source material when available ' +
        '(YouTube transcript for "yt_..." ids, article/newsletter full text for numeric ids). Use ids surfaced ' +
        'by read_archive_wiki_page wiki-links or search_archive results.',
      inputSchema: {
        id: z.string().describe('The archive item id, e.g. "17120704" or "yt_BSt010su3rU". Not the title.')
      }
    },
    async ({ id }) => {
      const item = getItem(config.archivePath, id)
      if (!item) {
        return text(`No archive item found with id "${id}". Ids come from wiki-links ([[<id>-<slug>|...]]) or search results.`)
      }
      return text(item.markdown)
    }
  )

  server.registerTool(
    'save_conversation_to_archive',
    {
      description:
        'File a conversation (or a distilled Q&A worth keeping) into the archive as a draft for human review. ' +
        'It lands in the wiki inbox — not the published wiki — where a curator promotes or discards it. ' +
        'Use when a user asks to save/file/archive the conversation or an answer. Pass topic as an exact ' +
        'wiki topic slug from list_archive_wiki_pages, if one fits.',
      inputSchema: {
        title: z.string().describe('Short descriptive title for the draft'),
        markdown: z.string().describe('The conversation or answer body, as markdown'),
        date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional().describe('YYYY-MM-DD; defaults to today'),
        source: z.string().optional().describe('Originating platform, e.g. "slack" or "nextspace"'),
        participants: z.array(z.string()).optional().describe('Who took part'),
        topic: z.string().optional().describe('Related wiki topic slug (exact, from list_archive_wiki_pages)')
      }
    },
    async (args) => {
      const { input, error } = validateConversation(args)
      if (!input) return text(`Could not save: ${error}`)
      const saved = saveConversation(config.archivePath, input)
      return text(`Draft filed for curator review at ${saved.path} (slug: ${saved.slug}).`)
    }
  )

  return server
}
