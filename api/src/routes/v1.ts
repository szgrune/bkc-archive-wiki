import { Router } from 'express'
import config from '../config.js'
import { listPages, readPage, isWikiSection, WIKI_SECTIONS } from '../core/wiki.js'
import { getItem, clearItemCaches } from '../core/items.js'
import { buildIndex, searchWiki, getIndexStats, isSearchableSection } from '../core/search.js'
import { saveConversation, validateConversation } from '../core/conversations.js'

const router = Router()

router.get('/health', (_req, res) => {
  res.json({ status: 'ok', archivePath: config.archivePath, index: getIndexStats() })
})

router.get('/search', (req, res) => {
  const q = String(req.query.q || '').trim()
  if (!q) {
    res.status(400).json({ error: 'bad_request', message: 'Missing required query param "q"' })
    return
  }
  const section = req.query.section ? String(req.query.section) : undefined
  if (section && !isSearchableSection(section)) {
    res.status(400).json({
      error: 'bad_request',
      message: `Unknown section "${section}". Valid: ${[...WIKI_SECTIONS, 'items'].join(', ')}`
    })
    return
  }
  const limit = Math.min(Math.max(Number(req.query.limit) || 10, 1), 50)
  const results = searchWiki(q, { section, limit })
  res.json({ query: q, count: results.length, results })
})

router.get('/pages', (req, res) => {
  const raw = req.query.section ? String(req.query.section) : undefined
  if (raw !== undefined && !isWikiSection(raw)) {
    res.status(400).json({
      error: 'bad_request',
      message: `Unknown section "${raw}". Valid: ${WIKI_SECTIONS.join(', ')}`
    })
    return
  }
  const pages = listPages(config.archivePath, raw !== undefined && isWikiSection(raw) ? raw : undefined)
  res.json({ count: pages.length, pages })
})

// Slug-only lookup searches all sections, mirroring read_archive_wiki_page.
router.get('/pages/:slug', (req, res) => {
  const page = readPage(config.archivePath, req.params.slug)
  if (!page) {
    res.status(404).json({ error: 'not_found', message: `No wiki page found for slug "${req.params.slug}"` })
    return
  }
  res.json(page)
})

router.get('/pages/:section/:slug', (req, res) => {
  const { section, slug } = req.params
  if (!isWikiSection(section)) {
    res.status(400).json({
      error: 'bad_request',
      message: `Unknown section "${section}". Valid: ${WIKI_SECTIONS.join(', ')}`
    })
    return
  }
  const page = readPage(config.archivePath, slug, section)
  if (!page) {
    res.status(404).json({ error: 'not_found', message: `No wiki page "${slug}" in section "${section}"` })
    return
  }
  res.json(page)
})

router.get('/items/:id', (req, res) => {
  const item = getItem(config.archivePath, req.params.id)
  if (!item) {
    res.status(404).json({ error: 'not_found', message: `No archive item found with id "${req.params.id}"` })
    return
  }
  res.json(item)
})

router.post('/conversations', (req, res) => {
  const { input, error } = validateConversation(req.body)
  if (!input) {
    res.status(400).json({ error: 'bad_request', message: error })
    return
  }
  const saved = saveConversation(config.archivePath, input)
  res.status(201).json(saved)
})

router.post('/reindex', (_req, res) => {
  clearItemCaches()
  const stats = buildIndex(config.archivePath)
  res.json({ status: 'ok', index: stats })
})

export default router
