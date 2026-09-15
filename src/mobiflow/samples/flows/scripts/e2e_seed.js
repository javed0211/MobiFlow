// onFlowStart — seed a test user via HTTP (Maestro GraalJS, not Node fetch).
// Env: API_BASE, USER_NAME  (passed by Maestro / mobiflow --env)

var seedUrl = (typeof API_BASE !== 'undefined' ? API_BASE : 'https://reqres.in') + '/api/users'
var seedName = typeof USER_NAME !== 'undefined' ? USER_NAME : 'MobiFlow E2E'

var seedResponse = http.post(seedUrl, {
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name: seedName, job: 'e2e' }),
})

output.seedStatus = seedResponse.status
try {
  output.createdUser = json(seedResponse.body)
  output.userId = String(output.createdUser.id || '')
} catch (e) {
  output.seedBody = seedResponse.body
  output.userId = ''
}
