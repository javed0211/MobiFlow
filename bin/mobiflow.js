#!/usr/bin/env node
/**
 * npm bin wrapper for the Python MobiFlow CLI.
 * Resolves: PATH mobiflow → python -m mobiflow → pip install → retry.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PKG = require("../package.json");
const VERSION = PKG.version || "0.1.0";
const REPO = "https://github.com/javed0211/MobiFlow.git";

function pyCandidates() {
  const fromEnv = process.env.MOBIFLOW_PYTHON;
  const list = [];
  if (fromEnv) list.push(fromEnv);
  if (process.platform === "win32") {
    list.push("py", "python3.12", "python3.11", "python", "python3");
  } else {
    list.push("python3.12", "python3.11", "python3", "python");
  }
  return [...new Set(list)];
}

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, {
    stdio: opts.stdio ?? "inherit",
    encoding: "utf8",
    shell: process.platform === "win32",
    env: process.env,
  });
}

function pythonVersion(py) {
  const r = run(
    py,
    ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
    { stdio: ["ignore", "pipe", "ignore"] }
  );
  if (r.status !== 0 || !r.stdout) return null;
  const parts = r.stdout.toString().trim().split(".").map(Number);
  return { major: parts[0], minor: parts[1], exe: null };
}

function whichPython() {
  for (const py of pyCandidates()) {
    const ver = pythonVersion(py);
    if (!ver || ver.major < 3 || ver.minor < 11) continue;
    const r = run(py, ["-c", "import sys; print(sys.executable)"], {
      stdio: ["ignore", "pipe", "ignore"],
    });
    if (r.status === 0 && r.stdout) {
      return r.stdout.toString().trim();
    }
  }
  return null;
}

function moduleAvailable(py) {
  const r = run(py, ["-c", "import mobiflow"], {
    stdio: ["ignore", "ignore", "ignore"],
  });
  return r.status === 0;
}

function pipInstall(py, spec) {
  console.error(`[mobiflow] Installing Python package: ${spec}`);
  const r = run(py, ["-m", "pip", "install", "--upgrade", spec], {
    stdio: "inherit",
  });
  return r.status === 0;
}

function ensureMobiflow(py) {
  if (moduleAvailable(py)) return true;

  const specs = [
    process.env.MOBIFLOW_PIP_SPEC,
    `mobiflow==${VERSION}`,
    "mobiflow",
    `git+${REPO}@v${VERSION}`,
    `git+${REPO}@main`,
  ].filter(Boolean);

  for (const spec of specs) {
    if (pipInstall(py, spec) && moduleAvailable(py)) return true;
  }
  return false;
}

function main(argv) {
  const py = whichPython();
  if (!py) {
    console.error(
      "[mobiflow] Python 3.11+ is required on PATH.\n" +
        "  https://www.python.org/downloads/\n" +
        "  Or set MOBIFLOW_PYTHON=/path/to/python3.12\n" +
        "  Or: pip install mobiflow && mobiflow --help"
    );
    process.exit(1);
  }

  // Prefer an already-installed console script on PATH (avoid recursion).
  const self = path.resolve(__filename);
  const onPath = run(
    process.platform === "win32" ? "where" : "which",
    ["mobiflow"],
    { stdio: ["ignore", "pipe", "ignore"] }
  );
  if (onPath.status === 0 && onPath.stdout) {
    const candidates = onPath.stdout
      .toString()
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    for (const bin of candidates) {
      let resolved = bin;
      try {
        resolved = fs.realpathSync(bin);
      } catch {
        /* ignore */
      }
      if (resolved === self) continue;
      if (resolved.includes(`${path.sep}node_modules${path.sep}`)) continue;
      if (resolved.includes(`${path.sep}mobiflow${path.sep}bin${path.sep}`)) {
        continue;
      }
      const r = run(bin, argv, { stdio: "inherit" });
      process.exit(r.status ?? 1);
    }
  }

  if (!ensureMobiflow(py)) {
    console.error(
      "[mobiflow] Could not install the Python package.\n" +
        `  Try: ${py} -m pip install "git+${REPO}@main"\n` +
        `  Or:  ${py} -m pip install mobiflow`
    );
    process.exit(1);
  }

  const r = run(py, ["-m", "mobiflow", ...argv], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

main(process.argv.slice(2));
