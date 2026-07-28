import fs from 'fs'
import path from 'path'
import { parseFrontmatter, truncate } from './wiki.js'

/**
 * Archive item resolution: stub in items/<year>/, plus full source material —
 * YouTube transcripts (collection/txt/youtube/) for "yt_..." ids, article/
 * newsletter full text (raw/archive.json) for everything else. Mirrors
 * llm_engine's get_archive_item.
 */

export const MAX_SOURCE_CHARS = 12000

export interface ArchiveItem {
  id: string
  kind: 'youtube' | 'item'
  title?: string
  url?: string
  date?: string
  markdown: string
  truncated: boolean
}

export function stripHtml(html: string): string {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#\d+;/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, '\n')
    .trim()
}

// Lazy per-archivePath caches of the two JSON indexes, keyed by item id.
const archiveJsonCache = new Map<string, Map<string, Record<string, unknown>>>()
const youtubeJsonCache = new Map<string, Map<string, Record<string, unknown>>>()

export function clearItemCaches(): void {
  archiveJsonCache.clear()
  youtubeJsonCache.clear()
}

function loadJsonItems(file: string): Record<string, unknown>[] {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'))
  return Array.isArray(data) ? data : data.items || []
}

function getArchiveJsonIndex(archivePath: string): Map<string, Record<string, unknown>> {
  let index = archiveJsonCache.get(archivePath)
  if (!index) {
    index = new Map()
    const file = path.join(archivePath, 'raw', 'archive.json')
    if (fs.existsSync(file)) {
      for (const item of loadJsonItems(file)) index.set(String(item.id), item)
    }
    archiveJsonCache.set(archivePath, index)
  }
  return index
}

function getYoutubeIndex(archivePath: string): Map<string, Record<string, unknown>> {
  let index = youtubeJsonCache.get(archivePath)
  if (!index) {
    index = new Map()
    const file = path.join(archivePath, 'collection', 'json', 'youtube.json')
    if (fs.existsSync(file)) {
      for (const item of loadJsonItems(file)) index.set(String(item.id), item)
    }
    youtubeJsonCache.set(archivePath, index)
  }
  return index
}

function getYoutubeTranscript(archivePath: string, id: string): string | null {
  const file = path.join(archivePath, 'collection', 'txt', 'youtube', `${id}.txt`)
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null
}

function findItemStub(archivePath: string, id: string): string | null {
  const itemsDir = path.join(archivePath, 'items')
  if (!fs.existsSync(itemsDir)) return null
  for (const year of fs.readdirSync(itemsDir)) {
    const yearDir = path.join(itemsDir, year)
    if (!fs.statSync(yearDir).isDirectory()) continue
    for (const name of fs.readdirSync(yearDir)) {
      if (name.startsWith(`${id}-`) || name === `${id}.md`) return path.join(yearDir, name)
    }
  }
  return null
}

export function getItem(archivePath: string, id: string): ArchiveItem | null {
  const parts: string[] = []
  let title: string | undefined
  let url: string | undefined
  let date: string | undefined
  let truncated = false

  const stubFile = findItemStub(archivePath, id)
  if (stubFile) {
    const raw = fs.readFileSync(stubFile, 'utf8').trim()
    const { meta } = parseFrontmatter(raw)
    title = meta.title || undefined
    url = meta.url || undefined
    date = meta.date || undefined
    parts.push(raw)
  }

  const kind: ArchiveItem['kind'] = id.startsWith('yt_') ? 'youtube' : 'item'

  if (kind === 'youtube') {
    const meta = getYoutubeIndex(archivePath).get(id)
    if (meta) {
      title = title || String(meta.title || '') || undefined
      url = url || String(meta.url || '') || undefined
      date = date || String(meta.date_published || '').slice(0, 10) || undefined
      if (!stubFile) {
        parts.push(
          `# ${meta.title}\n**Video:** ${meta.url} · **Published:** ${String(
            meta.date_published || ''
          ).slice(0, 10)}\n\n${stripHtml(String(meta.description || ''))}`
        )
      }
    }
    const transcriptText = getYoutubeTranscript(archivePath, id)
    if (transcriptText) {
      const t = truncate(transcriptText, MAX_SOURCE_CHARS)
      truncated = truncated || t.truncated
      parts.push(`## Transcript\n\n${t.text}`)
    }
  } else {
    const item = getArchiveJsonIndex(archivePath).get(id)
    if (item) {
      title = title || String(item.title || '') || undefined
      url = url || String(item.url || '') || undefined
      date = date || String(item.date_published || '').slice(0, 10) || undefined
      if (!stubFile) {
        parts.push(
          `# ${item.title}\n**URL:** ${item.url} · **Published:** ${String(
            item.date_published || ''
          ).slice(0, 10)} · **Tags:** ${((item.tags as string[]) || []).join(', ')}\n\n${stripHtml(
            String(item.description || '')
          )}`
        )
      }
      const content = stripHtml(String(item.content || ''))
      if (content) {
        const t = truncate(content, MAX_SOURCE_CHARS)
        truncated = truncated || t.truncated
        parts.push(`## Full text\n\n${t.text}`)
      }
    }
  }

  if (parts.length === 0) return null
  return { id, kind, title, url, date, markdown: parts.join('\n\n'), truncated }
}
