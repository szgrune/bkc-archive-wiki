import app from './app.js'
import config from './config.js'
import { buildIndex } from './core/search.js'

const stats = buildIndex(config.archivePath)
console.log(
  `Search index built: ${stats.pages} wiki pages, ${stats.items} item stubs (${config.archivePath})`
)

app.listen(config.port, () => {
  console.log(`archive-wiki-api listening on http://localhost:${config.port}`)
  if (!config.token) console.log('ARCHIVE_API_TOKEN not set — running without auth')
})
