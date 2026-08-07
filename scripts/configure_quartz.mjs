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
fs.writeFileSync(layoutPath, layout)

console.log(
  `Configured Quartz: baseUrl=${baseUrl}, globalGraph.depth=${graphDepth}, ` +
    `globalGraph.showTags=false, ogImages=${skipOgImages ? "off" : "on"}`,
)
