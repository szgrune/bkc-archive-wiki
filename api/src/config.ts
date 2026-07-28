import path from 'path'
import { fileURLToPath } from 'url'
import 'dotenv/config'

// src/ (or dist/) sits one level below the api/ package, which sits inside the wiki repo.
const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const config = {
  port: Number(process.env.PORT || 4000),
  archivePath: process.env.ARCHIVE_PATH
    ? path.resolve(process.env.ARCHIVE_PATH)
    : path.resolve(packageRoot, '..'),
  token: process.env.ARCHIVE_API_TOKEN || ''
}

export default config
