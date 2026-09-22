#!/usr/bin/env node

import fs from "node:fs"
import path from "node:path"

function usage(message) {
  if (message) console.error(`Error: ${message}`)
  console.error(
    "Usage: node scripts/configure_quartz.mjs <quartz-dir> --base-url <url> " +
      "[--graph-depth <n>] [--skip-og-images]",
  )
  process.exit(2)
}

const args = process.argv.slice(2)
const quartzDirArg = args.shift()
if (!quartzDirArg) usage("missing Quartz directory")

let baseUrl = ""
let graphDepth = 1
let skipOgImages = false

while (args.length > 0) {
  const option = args.shift()
  if (option === "--base-url") {
    baseUrl = args.shift() ?? usage("--base-url needs a value")
  } else if (option === "--graph-depth") {
    const value = args.shift()
    if (value === undefined || !/^\d+$/.test(value)) usage("--graph-depth must be an integer")
    graphDepth = Number(value)
  } else if (option === "--skip-og-images") {
    skipOgImages = true
  } else {
    usage(`unknown option: ${option}`)
  }
}

if (!baseUrl) usage("missing --base-url")
baseUrl = baseUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "")
if (!baseUrl) usage("--base-url cannot be empty")

const quartzDir = path.resolve(quartzDirArg)
const configPath = path.join(quartzDir, "quartz.config.ts")
const layoutPath = path.join(quartzDir, "quartz.layout.ts")

function readRequired(filePath) {
  if (!fs.existsSync(filePath)) usage(`not a Quartz checkout: missing ${filePath}`)
  return fs.readFileSync(filePath, "utf8")
}

function replaceRequired(source, pattern, replacement, description) {
  if (!pattern.test(source)) usage(`could not find Quartz ${description}; pinned layout may have changed`)
  return source.replace(pattern, replacement)
}

let config = readRequired(configPath)
config = replaceRequired(config, /pageTitle:\s*"[^"]*"/, 'pageTitle: "BKC Archive Wiki"', "pageTitle")
config = replaceRequired(config, /baseUrl:\s*"[^"]*"/, `baseUrl: "${baseUrl}"`, "baseUrl")

if (skipOgImages) {
  config = config.replace(
    /^(\s*)Plugin\.CustomOgImages\(\),.*$/m,
    "$1// Plugin.CustomOgImages(), // disabled for fast local previews",
  )
}
fs.writeFileSync(configPath, config)

let layout = readRequired(layoutPath)
layout = replaceRequired(
  layout,
  /^(\s*)Component\.Graph\(.*\),$/m,
  `$1Component.Graph({ globalGraph: { depth: ${graphDepth}, showTags: false } }),`,
  "Graph component",
)

// Explorer: hide `raw/` (a scanning surface for synthesis, not a reading
// destination) and pin the top-level order instead of sorting alphabetically.
// Everything not pinned keeps Quartz's default (folders first, then
// alphabetical), so nested levels are untouched.
//
// Two constraints shape what gets emitted below:
//   * sortFn/filterFn are serialized with .toString() and re-evaluated in the
//     browser, so they must be self-contained — no closing over outer scope,
//     and no `//` comments (the emitted call is collapsed onto one line).
//   * it must go out on a single line so the `.*` pattern matches an already
//     configured layout too — serve_site.sh reuses one .quartz-local checkout
//     across runs, so this script has to be re-runnable (as the Graph one is).
const explorerPinned = [
  "items",
  "orgs",
  "people",
  "topics",
  "events",
  "timeline",
  "sources",
  "log",
  "AGENTS",
  "README",
]
const explorerHidden = ["tags", "raw"]
const explorerOptions =
  `{ ` +
  `filterFn: (node) => !${JSON.stringify(explorerHidden)}.includes(node.slugSegment), ` +
  `sortFn: (a, b) => { ` +
  `const order = ${JSON.stringify(explorerPinned)}; ` +
  `const ai = order.indexOf(a.slugSegment); ` +
  `const bi = order.indexOf(b.slugSegment); ` +
  `if (ai !== -1 || bi !== -1) { ` +
  `if (ai === -1) return 1; ` +
  `if (bi === -1) return -1; ` +
  `return ai - bi; ` +
  `} ` +
  `if ((!a.isFolder && !b.isFolder) || (a.isFolder && b.isFolder)) { ` +
  `return a.displayName.localeCompare(b.displayName, undefined, { numeric: true, sensitivity: "base" }); ` +
  `} ` +
  `return !a.isFolder && b.isFolder ? 1 : -1; ` +
  `} }`
const explorerPattern = /^(\s*)Component\.Explorer\(.*\),$/gm
const explorerCount = (layout.match(explorerPattern) ?? []).length
if (explorerCount === 0) usage("could not find Quartz Explorer component; pinned layout may have changed")
layout = layout.replace(explorerPattern, `$1Component.Explorer(${explorerOptions}),`)

fs.writeFileSync(layoutPath, layout)

console.log(
  `Configured Quartz: baseUrl=${baseUrl}, globalGraph.depth=${graphDepth}, ` +
    `globalGraph.showTags=false, ogImages=${skipOgImages ? "off" : "on"}, ` +
    `explorer=${explorerCount} configured (raw hidden, top level pinned)`,
)
