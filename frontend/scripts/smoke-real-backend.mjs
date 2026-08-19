/**
 * Real-backend smoke for frontend integration (B3).
 * Uses the same paths as frontend/lib/api/* against NEXT_PUBLIC_API_BASE_URL.
 *
 * Usage (PowerShell):
 *   $env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000"
 *   $env:SMOKE_EMAIL = "admin@synq.dev"
 *   $env:SMOKE_PASSWORD = "AlphaAdmin123!"
 *   $env:SMOKE_TENANT = "alpha"
 *   node scripts/smoke-real-backend.mjs
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
const ORIGIN = BASE.replace(/\/api\/v1\/?$/, "")
const EMAIL = process.env.SMOKE_EMAIL ?? "admin@synq.dev"
const PASSWORD = process.env.SMOKE_PASSWORD ?? "AlphaAdmin123!"
const TENANT = process.env.SMOKE_TENANT ?? "alpha"
const MEMBER_EMAIL = process.env.SMOKE_MEMBER_EMAIL ?? "member@synq.dev"
const MEMBER_PASSWORD = process.env.SMOKE_MEMBER_PASSWORD ?? "AlphaMember123!"

function redactToken(value) {
  if (typeof value !== "string" || value.length < 24) return value
  return `${value.slice(0, 12)}…(${value.length} chars)`
}

function redact(obj) {
  if (!obj || typeof obj !== "object") return obj
  const out = Array.isArray(obj) ? [] : {}
  for (const [k, v] of Object.entries(obj)) {
    if (/token|password/i.test(k) && typeof v === "string") out[k] = redactToken(v)
    else if (v && typeof v === "object") out[k] = redact(v)
    else out[k] = v
  }
  return out
}

async function call(name, method, path, { token, body, base } = {}) {
  const url = `${base ?? BASE}${path}`
  const headers = { "Content-Type": "application/json" }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let json
  try {
    json = JSON.parse(text)
  } catch {
    json = null
  }
  const record = {
    name,
    request: { method, url, hasBearer: Boolean(token), body: body ?? null },
    status: res.status,
    response: json ?? text.slice(0, 800),
  }
  console.log(JSON.stringify({ ...record, response: redact(record.response) }, null, 2))
  console.log("---")
  return { ...record, ok: res.ok, json }
}

async function main() {
  const results = []

  const health = await fetch(BASE.replace(/\/api\/v1\/?$/, "") + "/health")
  const healthJson = await health.json().catch(() => ({}))
  console.log(
    JSON.stringify(
      { name: "GET /health", status: health.status, response: healthJson },
      null,
      2
    )
  )
  console.log("---")
  results.push({ name: "health", pass: health.ok })

  const login = await call("POST /auth/login (admin)", "POST", "/auth/login", {
    body: { email: EMAIL, password: PASSWORD, tenant_subdomain: TENANT },
  })
  results.push({ name: "login-admin", pass: login.ok && Boolean(login.json?.access_token) })
  let token = login.json?.access_token
  let email = EMAIL
  let password = PASSWORD
  let tenant = TENANT

  if (!token && (login.status === 422 || login.status === 404 || login.status === 401)) {
    const origin = BASE.replace(/\/api\/v1\/?$/, "")
    const bootstrapBody = {
      name: "Frontend smoke tenant",
      subdomain: process.env.SMOKE_BOOTSTRAP_SUBDOMAIN ?? "fesmoke",
      db_host: "localhost",
      db_name: process.env.SMOKE_BOOTSTRAP_DB ?? "frontend_smoke",
      db_user: "postgres",
      db_password: process.env.SMOKE_BOOTSTRAP_DB_PASSWORD ?? "postgres",
      admin_email: process.env.SMOKE_BOOTSTRAP_EMAIL ?? "admin@logicinnovationlabs.com",
      admin_display_name: "Frontend Smoke Admin",
    }
    const bootRes = await fetch(`${origin}/admin/tenants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bootstrapBody),
    })
    const bootText = await bootRes.text()
    let bootJson
    try {
      bootJson = JSON.parse(bootText)
    } catch {
      bootJson = null
    }
    console.log(
      JSON.stringify(
        {
          name: "POST /admin/tenants (bootstrap)",
          request: {
            method: "POST",
            url: `${origin}/admin/tenants`,
            body: { ...bootstrapBody, db_password: "(redacted)" },
          },
          status: bootRes.status,
          response: redact(bootJson ?? bootText.slice(0, 800)),
        },
        null,
        2
      )
    )
    console.log("---")
    results.push({ name: "bootstrap-tenant", pass: bootRes.ok && Boolean(bootJson?.temporary_password) })
    if (bootJson?.temporary_password && bootJson?.admin_email) {
      email = bootJson.admin_email
      password = bootJson.temporary_password
      tenant = bootstrapBody.subdomain
      const login2 = await call("POST /auth/login (bootstrapped admin)", "POST", "/auth/login", {
        body: { email, password, tenant_subdomain: tenant },
      })
      results.push({
        name: "login-admin-bootstrapped",
        pass: login2.ok && Boolean(login2.json?.access_token),
      })
      token = login2.json?.access_token
    }
  }

  if (!token) {
    console.log(JSON.stringify({ fatal: "no access_token; remaining calls skipped" }))
    console.log(JSON.stringify({ summary: results }, null, 2))
    process.exit(1)
  }

  const me = await call("GET /me", "GET", "/me", { token })
  results.push({
    name: "me",
    pass:
      me.ok &&
      me.json?.principal_id &&
      me.json?.tenant_id &&
      Array.isArray(me.json?.scopes),
  })

  const memberLogin = await call("POST /auth/login (member)", "POST", "/auth/login", {
    body: {
      email: MEMBER_EMAIL,
      password: MEMBER_PASSWORD,
      tenant_subdomain: TENANT,
    },
  })
  results.push({
    name: "login-member",
    pass: memberLogin.ok && Boolean(memberLogin.json?.access_token),
  })

  const registerMismatch = await call(
    "POST /admin/users (unauthenticated — expected fail)",
    "POST",
    "/admin/users",
    {
      body: {
        tenant_subdomain: TENANT,
        email: "nobody@example.test",
        password: "not-a-real-signup",
        display_name: "Should Fail",
      },
    }
  )
  results.push({
    name: "register-blocked",
    pass: registerMismatch.status === 401 || registerMismatch.status === 403,
  })

  const search = await call("POST /search/federated", "POST", "/search/federated", {
    token,
    body: { query: "invoice", size: 5, enable_lexical: true, enable_vector: true },
  })
  results.push({
    name: "search",
    pass: search.ok && Array.isArray(search.json?.results),
  })

  const docId = search.json?.results?.[0]?.document_id
  if (docId) {
    const doc = await call("GET /document/{id}", "GET", `/document/${encodeURIComponent(docId)}`, {
      token,
    })
    results.push({
      name: "document",
      pass: doc.status === 200 || doc.status === 403 || doc.status === 404,
    })
  } else {
    results.push({ name: "document", pass: false, note: "no federated hit to open" })
  }

  const chat = await call(
    "POST /assistant/orchestrator/chat",
    "POST",
    "/assistant/orchestrator/chat",
    {
      token,
      body: { prompt: "What invoices are outstanding?", session_id: `smoke-${Date.now()}` },
    }
  )
  const chatText =
    typeof chat.response === "string"
      ? chat.response
      : JSON.stringify(chat.response)
  results.push({
    name: "chat",
    pass: chat.ok && (chatText.includes('"type": "final"') || chatText.includes('"type":"final"')),
  })

  const connectors = await call(
    "GET /connectors/google_drive/status",
    "GET",
    "/connectors/google_drive/status",
    { token, base: ORIGIN }
  )
  results.push({
    name: "connectors",
    pass: connectors.ok && connectors.json?.source_type === "google_drive",
  })

  const users = await call("GET /admin/users", "GET", "/admin/users", { token })
  results.push({ name: "admin-users", pass: users.ok && Array.isArray(users.json) })

  const audit = await call("GET /admin/audit", "GET", "/admin/audit?page=1&page_size=5", {
    token,
  })
  results.push({
    name: "admin-audit",
    pass: audit.ok && Array.isArray(audit.json?.items),
  })

  const oauthToken = await call(
    "POST /oauth/token refresh (expected 501)",
    "POST",
    "/oauth/token",
    {
      body: undefined,
    }
  )
  // apiFetch would JSON this; backend wants form. Record that frontend does not call it.
  results.push({
    name: "oauth-token-json",
    pass: true,
    note: `status ${oauthToken.status} — frontend does not implement refresh; grant is 501 on Block A`,
  })

  console.log(JSON.stringify({ summary: results }, null, 2))
  const failed = results.filter((r) => r.pass === false)
  process.exit(failed.length ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
