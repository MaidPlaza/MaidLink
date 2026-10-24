import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'

const TOKEN_KEY = /^[A-Z0-9_]+$/
const IS_MARKUP = /^\s*</
const HAS_WS = /\s/
const cssVarOf = (key: string) => '--' + key
  .split('.')
  .map((seg) => seg
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/_/g, '-')
    .toLowerCase())
  .join('-')
const UI_STRUCTURE = fileURLToPath(new URL('./electron/configs/UIStructure.json', import.meta.url))
const VIRTUAL_ID = 'virtual:ui-colors.css'
const RESOLVED_ID = '\0' + VIRTUAL_ID

const MARKUP_CONFIG = fileURLToPath(new URL('./electron/configs/markup.json', import.meta.url))

function markupConfigReload(): Plugin {
  return {
    name: 'markup-config-reload',
    configureServer(server) {
      server.watcher.add(MARKUP_CONFIG)
      server.watcher.on('change', (file) => {
        if (file === MARKUP_CONFIG) server.ws.send({ type: 'full-reload' })
      })
    },
  }
}

function uiColorsCss(): Plugin {
  function build(): string {
    const json = JSON.parse(readFileSync(UI_STRUCTURE, 'utf8')) as Record<string, unknown>
    const vars: string[] = []
    for (const [key, value] of Object.entries(json)) {
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        for (const [path, v] of Object.entries(value as Record<string, unknown>)) {
          if (typeof v === 'string' && v && !IS_MARKUP.test(v) && !HAS_WS.test(path)) vars.push(`  ${cssVarOf(path)}: ${v};`)
        }
        continue
      }
      if (typeof value === 'string' && value && TOKEN_KEY.test(key)) {
        vars.push(`  ${cssVarOf(key)}: ${value};`)
      }
    }
    return `:root {\n${vars.join('\n')}\n}\n`
  }
  return {
    name: 'ui-colors-css',
    resolveId(id) {
      return id === VIRTUAL_ID ? RESOLVED_ID : null
    },
    load(id) {
      return id === RESOLVED_ID ? build() : null
    },
    configureServer(server) {
      server.watcher.add(UI_STRUCTURE)
      server.watcher.on('change', (file) => {
        if (file === UI_STRUCTURE) {
          const mod = server.moduleGraph.getModuleById(RESOLVED_ID)
          if (mod) server.moduleGraph.invalidateModule(mod)
          server.ws.send({ type: 'full-reload' })
        }
      })
    },
  }
}

const TERMS_FILE = fileURLToPath(new URL('../TERMS.txt', import.meta.url))
const TERMS_ID = 'virtual:terms'
const TERMS_RESOLVED = '\0' + TERMS_ID

function termsText(): Plugin {
  return {
    name: 'terms-text',
    resolveId(id) {
      return id === TERMS_ID ? TERMS_RESOLVED : null
    },
    load(id) {
      if (id !== TERMS_RESOLVED) return null
      this.addWatchFile(TERMS_FILE)
      return `export default ${JSON.stringify(readFileSync(TERMS_FILE, 'utf8'))}`
    },
  }
}

export default defineConfig({
  plugins: [react(), uiColorsCss(), markupConfigReload(), termsText()],
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./', import.meta.url)),
    },
  },
  server: { port: 5173, strictPort: true, host: '127.0.0.1' },
})
