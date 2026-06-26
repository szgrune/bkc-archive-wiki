#!/usr/bin/env node
// build.mjs — deterministic generator for the BKC Archive Wiki.
//
// Reads the immutable source (raw/archive.json) and writes the SCRIPT-OWNED
// layer of the wiki: one stub page per item plus a few deterministic indexes.
// It NEVER touches LLM-owned pages (topics/, people/, orgs/, narratives,
// index.md, log.md, AGENTS.md, README.md). Safe + idempotent to re-run.
//
// Usage (from archive-wiki/ or anywhere):
//   node scripts/build.mjs                 # default: --year=2025 (prototype slice)
//   node scripts/build.mjs --year=2024
//   node scripts/build.mjs --all           # every item, all years
//   node scripts/build.mjs --input=raw/archive.json
//
// Counts, digests and tag tables are ALWAYS computed corpus-wide; only the
// per-item stub pages are gated by --year/--all.

import { readFileSync, writeFileSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const WIKI_ROOT = resolve(SCRIPT_DIR, "..");           // archive-wiki/

// ---- args -----------------------------------------------------------------
const args = process.argv.slice(2);
const getFlag = (name) => {
  const hit = args.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
  if (!hit) return undefined;
  const eq = hit.indexOf("=");
  return eq === -1 ? true : hit.slice(eq + 1);
};
const ALL = getFlag("all") === true;
const YEAR = ALL ? null : String(getFlag("year") ?? "2025");
const INPUT = resolve(WIKI_ROOT, String(getFlag("input") ?? "raw/archive.json"));

// ---- helpers --------------------------------------------------------------
const write = (relPath, content) => {
  const full = join(WIKI_ROOT, relPath);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, content);
};

const ENTITIES = {
  "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
  "&#x27;": "'", "&apos;": "'", "&nbsp;": " ", "&mdash;": "—",
  "&ndash;": "–", "&hellip;": "…", "&rsquo;": "’", "&lsquo;": "‘",
  "&ldquo;": "“", "&rdquo;": "”",
};
const unescapeHtml = (s) =>
  s
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&[a-z#0-9]+;/gi, (m) => ENTITIES[m.toLowerCase()] ?? m);

// HTML description -> compact markdown (links preserved, tags stripped).
const cleanDescription = (html) => {
  if (!html) return "";
  let s = String(html);
  s = s.replace(/<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi,
    (_, href, txt) => `[${txt.replace(/<[^>]+>/g, "").trim()}](${href})`);
  s = s.replace(/<\/(p|div|br|li|h[1-6])\s*>/gi, "\n");
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<[^>]+>/g, "");
  s = unescapeHtml(s);
  s = s.replace(/\r/g, "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n");
  return s.trim();
};

const domainOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "unknown";
  }
};

const slugify = (s, max = 60) =>
  String(s)
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/['’]/g, "")
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, max)
    .replace(/-+$/g, "");

const yamlStr = (s) => `"${String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;

// Neutralize #hashtags in plain text (e.g. item titles) so Quartz/Obsidian don't
// auto-link them as topic tags. Escapes a "#" that starts a tag-like token (at the
// start of the string or after whitespace, followed by a word char). Leaves things
// like "C#" and URL anchors untouched.
const escapeHashtags = (s) => String(s).replace(/(^|\s)#(?=[\w-])/g, "$1\\#");

const splitAuthors = (a) =>
  !a ? [] : String(a).split(",").map((x) => x.trim()).filter(Boolean);

// ---- load -----------------------------------------------------------------
if (!existsSync(INPUT)) {
  console.error(`Source not found: ${INPUT}`);
  process.exit(1);
}
const data = JSON.parse(readFileSync(INPUT, "utf8"));
const items = data.items ?? [];
console.log(`Loaded ${items.length} items from ${INPUT}`);

// Pre-compute a stub name (id-slug) for every item so links are stable + shared
// between item pages and the digest.
const enrich = (it) => {
  const date = (it.date_published || "").slice(0, 10);
  const year = date.slice(0, 4) || "undated";
  const domain = domainOf(it.url);
  const titleRaw = (it.title || "").trim();
  // Display title: decode HTML entities (&amp; -> &, etc.) for clean rendering.
  // Slug stays derived from titleRaw so stub filenames remain stable.
  const title = unescapeHtml(titleRaw) || `Untitled — ${domain}`;
  const baseSlug = slugify(titleRaw) || `untitled-${slugify(domain)}`;
  const stub = `${it.id}-${baseSlug}`;
  return { ...it, _date: date, _year: year, _domain: domain, _title: title, _stub: stub };
};
const all = items.map(enrich);

// ---- 1. item stubs (gated by --year/--all) --------------------------------
const selected = ALL ? all : all.filter((it) => it._year === YEAR);

// Clean the slice's output dir(s) so renames/removals don't leave orphans.
const yearsToClean = ALL ? [...new Set(all.map((i) => i._year))] : [YEAR];
for (const y of yearsToClean) {
  const dir = join(WIKI_ROOT, "items", y);
  if (existsSync(dir)) rmSync(dir, { recursive: true, force: true });
}

let written = 0;
for (const it of selected) {
  const authors = splitAuthors(it.authors);
  const feedTags = Array.isArray(it.tags) ? it.tags : [];
  const desc = cleanDescription(it.description);

  const fm = [
    "---",
    `id: ${it.id}`,
    "type: item",
    `title: ${yamlStr(it._title)}`,
    `url: ${yamlStr(it.url)}`,
    `source: ${it._domain}`,
    `date: ${it._date || "unknown"}`,
    `authors: [${authors.map(yamlStr).join(", ")}]`,
    `feed_tags: [${feedTags.map(yamlStr).join(", ")}]`,
    "---",
  ].join("\n");

  const metaLine =
    `**Source:** [${it._domain}](${it.url}) · **Published:** ${it._date || "unknown"}` +
    (authors.length ? ` · **By:** ${authors.join(", ")}` : "") +
    (feedTags.length ? ` · **Feed tags:** ${feedTags.join(", ")}` : "");

  const body = [
    fm,
    "",
    `# ${escapeHashtags(it._title)}`,
    "",
    metaLine,
    "",
    desc ? `> ${desc.replace(/\n/g, "\n> ")}\n` : "",
    `[Open original ›](${it.url})`,
    "",
  ].join("\n");

  write(join("items", it._year, `${it._stub}.md`), body);
  written++;
}
console.log(`Wrote ${written} item stubs (${ALL ? "all years" : `year ${YEAR}`}).`);

// ---- 2. digest (corpus-wide, sharded by year) -----------------------------
const byYear = new Map();
for (const it of all) {
  if (!byYear.has(it._year)) byYear.set(it._year, []);
  byYear.get(it._year).push(it);
}
const years = [...byYear.keys()].sort();

for (const y of years) {
  const rows = byYear
    .get(y)
    .sort((a, b) => (a._date < b._date ? 1 : -1)) // newest first
    .map((it) => {
      const tags = (it.tags || []).join(", ");
      return `- [[${it._stub}|${it._title.replace(/\|/g, "/")}]] — ${it._date} · ${it._domain}${tags ? ` · ${tags}` : ""}`;
    });
  write(
    join("raw", "digest", `${y}.md`),
    `# Digest — ${y} (${rows.length} items)\n\n` +
      `> Scanning surface for clustering. One row per item: link · date · domain · feed-tags.\n` +
      `> Copy a \`[[stub|Title]]\` link verbatim into a topic/person/org page.\n\n` +
      rows.join("\n") +
      "\n"
  );
}
write(
  join("raw", "digest.md"),
  `# Digest index\n\nPer-year scanning surfaces for the synthesis layer.\n\n` +
    years
      .map((y) => `- [[raw/digest/${y}|${y}]] — ${byYear.get(y).length} items → \`raw/digest/${y}.md\``)
      .join("\n") +
    "\n"
);

// ---- 2b. seed a navigational landing page per year if absent --------------
// LLM-owned (like index.md/log.md): seed-if-absent so hand-written year
// narratives (e.g. timeline/2025.md) are never overwritten.
for (const y of years) {
  const rel = join("timeline", `${y}.md`);
  if (!existsSync(join(WIKI_ROOT, rel))) {
    const n = byYear.get(y).length;
    write(
      rel,
      `---\ntype: year\ntitle: ${y}\nitem_count: ${n}\n---\n` +
        `# ${y}\n\n` +
        `${n} items. Navigational landing page — thematic synthesis pending.\n\n` +
        `## Navigate\n` +
        `All ${y} sources: \`items/${y}/\` · scanning surface: \`raw/digest/${y}.md\` · ` +
        `counts: [[_counts|Timeline counts]]\n`
    );
  }
}

// ---- 3. sources/_domains.md -----------------------------------------------
const domCount = new Map();
for (const it of all) domCount.set(it._domain, (domCount.get(it._domain) || 0) + 1);
const domSorted = [...domCount.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
write(
  join("sources", "_domains.md"),
  `# Sources by domain\n\n` +
    `_Deterministic — generated by \`scripts/build.mjs\`. ${domCount.size} unique domains, ` +
    `${all.length} items._\n\n` +
    `| Domain | Items |\n| --- | ---: |\n` +
    domSorted.map(([d, c]) => `| ${d} | ${c} |`).join("\n") +
    "\n"
);

// ---- 4. timeline/_counts.md -----------------------------------------------
const monthCount = new Map();
for (const it of all) {
  const ym = it._date.slice(0, 7) || "unknown";
  monthCount.set(ym, (monthCount.get(ym) || 0) + 1);
}
const yearRows = years.map((y) => `| [[timeline/${y}|${y}]] | ${byYear.get(y).length} |`);
const monthRows = [...monthCount.entries()]
  .sort((a, b) => a[0].localeCompare(b[0]))
  .map(([m, c]) => `| ${m} | ${c} |`);
write(
  join("timeline", "_counts.md"),
  `# Timeline counts\n\n_Deterministic — generated by \`scripts/build.mjs\`._\n\n` +
    `## Items per year\n\n| Year | Items |\n| --- | ---: |\n${yearRows.join("\n")}\n\n` +
    `## Items per month\n\n| Month | Items |\n| --- | ---: |\n${monthRows.join("\n")}\n`
);

// ---- 5. raw/feed-tags.md --------------------------------------------------
const tagCount = new Map();
for (const it of all) for (const t of it.tags || []) tagCount.set(t, (tagCount.get(t) || 0) + 1);
const tagSorted = [...tagCount.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
write(
  join("raw", "feed-tags.md"),
  `# Feed tags (folksonomy)\n\n` +
    `_Deterministic. These are the source feed's workflow/newsletter tags — NOT topical._\n\n` +
    `| Tag | Items |\n| --- | ---: |\n` +
    tagSorted.map(([t, c]) => `| ${t} | ${c} |`).join("\n") +
    "\n"
);

// ---- 6. seed LLM-owned index.md / log.md only if absent -------------------
if (!existsSync(join(WIKI_ROOT, "log.md"))) {
  const today = new Date().toISOString().slice(0, 10);
  write(
    "log.md",
    `# Log\n\nAppend-only. Entry prefix: \`## [YYYY-MM-DD] <op> | <detail>\`.\n\n` +
      `## [${today}] build | scaffolded wiki via scripts/build.mjs\n`
  );
}
if (!existsSync(join(WIKI_ROOT, "index.md"))) {
  write(
    "index.md",
    `# Index\n\n_Catalog of the wiki. Maintained by the LLM; drill in from here._\n\n` +
      `## Reference (generated)\n` +
      `- [[_domains|Sources by domain]]\n- [[_counts|Timeline counts]]\n` +
      `- [[feed-tags|Feed tags]]\n- [[digest|Digest index]]\n\n` +
      `## Topics\n_none yet_\n\n## People\n_none yet_\n\n## Organizations\n_none yet_\n\n` +
      `## Events\n_none yet_\n`
  );
}

console.log("Done.");
