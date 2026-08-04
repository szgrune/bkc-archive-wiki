import fs from 'fs'
import path from 'path'
import MiniSearch from 'minisearch'
import { WIKI_SECTIONS, parseFrontmatter } from './wiki.js'

/**
 * Lexical search over the wiki: curated pages (frontmatter + body) and
 * archive item stubs (metadata). In-memory MiniSearch index, built at startup
 * and rebuilt on demand (POST /v1/reindex). The /v1/search contract is
 * retrieval-agnostic — this implementation can be swapped for vectors later
 * without changing clients.
 */

export interface SearchResult {
  section: string
  slug: string
  title: string
  score: number
  snippet: string
  /** Archive item id, present when section === 'items'. */
  id?: string
}

export interface IndexStats {
  pages: number
  items: number
  builtAt: string
}

interface IndexedDoc {
  key: string
  section: string
  slug: string
  title: string
  itemId?: string
  body: string
  tags: string
}

const SEARCHABLE_SECTIONS = [...WIKI_SECTIONS, 'items']

let mini: MiniSearch<IndexedDoc> | null = null
let bodies = new Map<string, string>()
let stats: IndexStats = { pages: 0, items: 0, builtAt: '' }

export function isSearchableSection(value: string): boolean {
  return SEARCHABLE_SECTIONS.includes(value)
}

export function buildIndex(archivePath: string): IndexStats {
  const docs: IndexedDoc[] = []
  const nextBodies = new Map<string, string>()
  let pages = 0
  let items = 0

  for (const section of WIKI_SECTIONS) {
    const dir = path.join(archivePath, section)
    if (!fs.existsSync(dir)) continue
    for (const name of fs.readdirSync(dir).sort()) {
      if (!name.endsWith('.md') || name.startsWith('_')) continue
      const { meta, body } = parseFrontmatter(fs.readFileSync(path.join(dir, name), 'utf8'))
      const slug = name.replace(/\.md$/, '')
      const key = `${section}/${slug}`
      docs.push({
        key,
        section,
        slug,
        title: meta.title || slug,
        body,
        tags: [meta.related, meta.related_topics, meta.affiliations].filter(Boolean).join(' ')
      })
      nextBodies.set(key, body)
      pages += 1
    }
  }

  const itemsDir = path.join(archivePath, 'items')
  if (fs.existsSync(itemsDir)) {
    for (const year of fs.readdirSync(itemsDir).sort()) {
      const yearDir = path.join(itemsDir, year)
      if (!fs.statSync(yearDir).isDirectory()) continue
      for (const name of fs.readdirSync(yearDir).sort()) {
        if (!name.endsWith('.md')) continue
        const { meta, body } = parseFrontmatter(fs.readFileSync(path.join(yearDir, name), 'utf8'))
        const slug = name.replace(/\.md$/, '')
        const key = `items/${slug}`
        docs.push({
          key,
          section: 'items',
          slug,
          title: meta.title || slug,
          itemId: meta.id || slug.split('-')[0],
          body,
          tags: meta.feed_tags || ''
        })
        nextBodies.set(key, body)
        items += 1
      }
    }
  }

  const next = new MiniSearch<IndexedDoc>({
    idField: 'key',
    fields: ['title', 'body', 'tags'],
    storeFields: ['section', 'slug', 'title', 'itemId'],
    searchOptions: { boost: { title: 3, tags: 2 }, prefix: true }
  })
  next.addAll(docs)

  mini = next
  bodies = nextBodies
  stats = { pages, items, builtAt: new Date().toISOString() }
  return stats
}

export function getIndexStats(): IndexStats {
  return stats
}

function makeSnippet(body: string, query: string, width = 200): string {
  const text = body.replace(/\s+/g, ' ').trim()
  const lower = text.toLowerCase()
  const terms = query
    .toLowerCase()
    .split(/\W+/)
    .filter((t) => t.length > 2)
  let pos = -1
  for (const term of terms) {
    const i = lower.indexOf(term)
    if (i !== -1 && (pos === -1 || i < pos)) pos = i
  }
  if (pos === -1) return text.slice(0, width)
  const start = Math.max(0, pos - Math.floor(width / 3))
  const end = Math.min(text.length, start + width)
  return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`
}

export function searchWiki(
  query: string,
  options: { section?: string; limit?: number } = {}
): SearchResult[] {
  if (!mini) throw new Error('Search index not built yet')
  const { section, limit = 10 } = options
  const raw = mini.search(query, {
    filter: section ? (result) => result.section === section : undefined
  })
  // MiniSearch's result `id` is the document key (idField: 'key').
  return raw.slice(0, limit).map((r) => ({
    section: r.section,
    slug: r.slug,
    title: r.title,
    id: r.itemId || undefined,
    score: Math.round(r.score * 1000) / 1000,
    snippet: makeSnippet(bodies.get(String(r.id)) ?? '', query)
  }))
}
