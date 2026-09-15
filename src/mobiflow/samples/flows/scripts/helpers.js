// MobiFlow Maestro helpers (GraalJS sandbox — no Node.js APIs)
// Use via: - runScript: scripts/helpers.js
// Values on `output` are available later as ${output.key}
//
// HTTP (E2E / hooks) — Maestro built-ins, not fetch/axios:
//   var res = http.get(API_BASE + '/health')
//   var res = http.post(API_BASE + '/users', { headers: { Authorization: 'Bearer ' + TOKEN }, body: JSON.stringify({ email: USER_EMAIL }) })
//   output.user = json(res.body)
// Put setup in onFlowStart and teardown in onFlowComplete.

output.runId = 'run-' + Date.now()
output.ready = true
