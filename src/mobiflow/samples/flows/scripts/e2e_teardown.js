// onFlowComplete — delete the seeded user (runs on pass or fail).

var base = typeof API_BASE !== 'undefined' ? API_BASE : 'https://reqres.in'
var uid = output.userId ? String(output.userId) : ''
if (!uid) {
  output.teardownSkipped = true
} else {
  var teardownResponse = http.delete(base + '/api/users/' + uid)
  output.teardownStatus = teardownResponse.status
}
