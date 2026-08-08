// MobiFlow Maestro helpers (GraalJS sandbox — no Node.js APIs)
// Use via: - runScript: scripts/helpers.js
// Values set on `output` are available later as ${output.key}

function setOutput(key, value) {
  output[key] = value;
  return value;
}

function nowIso() {
  return new Date().toISOString();
}

// Example: setOutput('runId', 'run-' + Date.now());
