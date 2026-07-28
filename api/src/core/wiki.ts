import fs from 'fs'
import path from 'path'

/**
 * Read access to the curated wiki layer. Mirrors the behavior of
 * llm_engine's src/agents/tools/archive.ts (list_archive_wiki_pages /
 * read_archive_wiki_page), with `events` added now that the section exists.
 */

export const WIKI_SECTIONS = ['topics', 'people', 'orgs', 'events', 'timeline'] as const
export type WikiSection = (typeof WIKI_SECTIONS)[number]

export const MAX_PAGE_CHARS = 8000

export interface PageSummary {
  section: WikiSection
  slug: string
  title: string
  meta: Record<string, string>
}

export interface Page {
  section: WikiSection
  slug: string
  frontmatter: Record<string, string>
  markdown: string
  truncated: boolean
}

export function isWikiSection(value: string): value is WikiSection {
  return (WIKI_SECTIONS as readonly string[]).includes(value)
}

export function parseFrontmatter(raw: string): { meta: Record<string, string>; body: string } {
  const meta: Record<string, string> = {}
  let body = raw
  if (raw.startsWith('---')) {
    const end = raw.indexOf('\n---', 3)
    if (end !== -1) {
      const fm = raw.slice(3, end)
      body = raw.slice(end + 4).trim()
      for (const line of fm.split('\n')) {
        const m = line.match(/^([a-z_]+):\s*(.*)$/i)
        if (m) meta[m[1]] = m[2].trim().replace(/^["']|["']$/g, '')
      }
    }
  }
  return { meta, body }
}

export function truncate(text: string, max: number): { text: string; truncated: boolean } {
  if (text.length <= max) return { text, truncated: false }
  return {
    text: `${text.slice(0, max)}\n\n[... truncated: ${text.length - max} more characters]`,
    truncated: true
  }
}

export function listPages(archivePath: string, section?: WikiSection): PageSummary[] {
  const sections = section ? [section] : [...WIKI_SECTIONS]
  const pages: PageSummary[] = []
  for (const s of sections) {
    const dir = path.join(archivePath, s)
    if (!fs.existsSync(dir)) continue
    for (const name of fs.readdirSync(dir).sort()) {
      if (!name.endsWith('.md') || name.startsWith('_')) continue
      const { meta } = parseFrontmatter(fs.readFileSync(path.join(dir, name), 'utf8'))
      const slug = name.replace(/\.md$/, '')
      pages.push({ section: s, slug, title: meta.title || slug, meta })
    }
  }
  return pages
}

export function readPage(archivePath: string, slug: string, section?: WikiSection): Page | null {
  const sections = section ? [section] : [...WIKI_SECTIONS]
  for (const s of sections) {
    const file = path.join(archivePath, s, `${slug}.md`)
    if (!fs.existsSync(file)) continue
    const raw = fs.readFileSync(file, 'utf8')
    const { meta } = parseFrontmatter(raw)
    const { text, truncated } = truncate(raw, MAX_PAGE_CHARS)
    return { section: s, slug, frontmatter: meta, markdown: text, truncated }
  }
  return null
}
