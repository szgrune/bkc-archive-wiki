import fs from 'fs'
import path from 'path'

/**
 * Push-back: conversations filed from an LLM engine land as draft markdown
 * in inbox/conversations/ for human review — never directly in the published
 * wiki. See AGENTS.md §"The inbox" for the promotion workflow.
 */

export interface ConversationInput {
  title: string
  markdown: string
  /** YYYY-MM-DD; defaults to today. */
  date?: string
  /** Originating platform, e.g. "slack" or "nextspace". */
  source?: string
  participants?: string[]
  /** Related wiki topic slug, if known. */
  topic?: string
}

export interface SavedConversation {
  slug: string
  /** Path relative to the wiki root, e.g. "inbox/conversations/2026-07-16-foo.md". */
  path: string
}

const INBOX_DIR = path.join('inbox', 'conversations')
const MAX_SLUG_CHARS = 60

export function validateConversation(body: unknown): { input?: ConversationInput; error?: string } {
  if (typeof body !== 'object' || body === null) return { error: 'Request body must be a JSON object' }
  const b = body as Record<string, unknown>
  if (typeof b.title !== 'string' || !b.title.trim()) return { error: '"title" is required (non-empty string)' }
  if (typeof b.markdown !== 'string' || !b.markdown.trim()) {
    return { error: '"markdown" is required (non-empty string, the conversation body)' }
  }
  if (b.date !== undefined && (typeof b.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(b.date))) {
    return { error: '"date" must be a YYYY-MM-DD string' }
  }
  for (const field of ['source', 'topic'] as const) {
    if (b[field] !== undefined && typeof b[field] !== 'string') return { error: `"${field}" must be a string` }
  }
  if (
    b.participants !== undefined &&
    (!Array.isArray(b.participants) || b.participants.some((p) => typeof p !== 'string'))
  ) {
    return { error: '"participants" must be an array of strings' }
  }
  return {
    input: {
      title: b.title.trim(),
      markdown: b.markdown.trim(),
      date: b.date as string | undefined,
      source: b.source ? String(b.source).trim() : undefined,
      participants: b.participants as string[] | undefined,
      topic: b.topic ? String(b.topic).trim() : undefined
    }
  }
}

function slugify(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG_CHARS)
    .replace(/-+$/, '')
  return slug || 'conversation'
}

function yamlString(value: string): string {
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\s+/g, ' ')}"`
}

export function saveConversation(archivePath: string, input: ConversationInput): SavedConversation {
  const date = input.date || new Date().toISOString().slice(0, 10)
  const dir = path.join(archivePath, INBOX_DIR)
  fs.mkdirSync(dir, { recursive: true })

  const base = `${date}-${slugify(input.title)}`
  let slug = base
  for (let n = 2; fs.existsSync(path.join(dir, `${slug}.md`)); n += 1) {
    slug = `${base}-${n}`
  }

  const fm = [
    '---',
    'type: conversation',
    'status: draft',
    `title: ${yamlString(input.title)}`,
    `date: ${date}`,
    input.source ? `source: ${slugify(input.source)}` : null,
    input.participants?.length
      ? `participants: [${input.participants.map((p) => p.replace(/[\[\],\n]/g, ' ').trim()).join(', ')}]`
      : null,
    input.topic ? `related_topics: [${slugify(input.topic)}]` : null,
    `filed: ${new Date().toISOString()}`,
    '---'
  ].filter((line): line is string => line !== null)

  const file = path.join(dir, `${slug}.md`)
  fs.writeFileSync(file, `${fm.join('\n')}\n\n${input.markdown}\n`, 'utf8')
  return { slug, path: path.join(INBOX_DIR, `${slug}.md`) }
}
