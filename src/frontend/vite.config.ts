import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Written by src/devserver.py while the dev backend is running.
const RUNTIME_FILE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '.nconotes-dev.json',
)

interface DevRuntime {
  port: number
  token: string
}

function readRuntime(): DevRuntime | null {
  try {
    return JSON.parse(readFileSync(RUNTIME_FILE, 'utf-8')) as DevRuntime
  } catch {
    return null
  }
}

function jsonError(res: http.ServerResponse, status: number, error: string, detail: string) {
  res.statusCode = status
  res.setHeader('content-type', 'application/json')
  res.end(JSON.stringify({ error, detail }))
}

// Forwards /api requests to the dev backend, attaching the auth token.
//
// The backend picks a random port and token on every start, so both are read from
// the runtime file per request rather than captured at config time — restarting the
// backend needs no Vite restart. In the packaged app there is no proxy: pywebview
// injects the token directly and the frontend talks to the backend on its own origin.
function backendProxy(): Plugin {
  return {
    name: 'nconotes-backend-proxy',
    configureServer(server) {
      server.middlewares.use('/api', (req, res) => {
        const runtime = readRuntime()
        if (!runtime) {
          jsonError(
            res,
            503,
            'backend_unavailable',
            'Dev backend is not running. Start it with: python src/devserver.py',
          )
          return
        }

        const proxied = http.request(
          {
            host: '127.0.0.1',
            port: runtime.port,
            // connect strips the '/api' mount prefix from req.url; restore it.
            path: '/api' + (req.url ?? ''),
            method: req.method,
            headers: {
              ...req.headers,
              host: `127.0.0.1:${runtime.port}`,
              'x-nconotes-token': runtime.token,
            },
          },
          (backendRes) => {
            res.writeHead(backendRes.statusCode ?? 502, backendRes.headers)
            backendRes.pipe(res)
          },
        )

        proxied.on('error', (err) => {
          jsonError(res, 502, 'proxy_error', err.message)
        })

        req.pipe(proxied)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), backendProxy()],
})
