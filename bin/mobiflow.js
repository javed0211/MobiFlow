#!/usr/bin/env node
/**
 * npm launcher for the MobiFlow engine (Python), which is shipped inside
 * this package (pyproject.toml + src/mobiflow). No git clone.
 *
 * Windows note: never run ``python -c "…"`` through ``cmd.exe`` (shell:true) —
 * quoting breaks and a real 3.12 install looks like “no Python 3.11+”.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PKG = require("../package.json");
const VERSION = PKG.version || "0.1.0";
const ROOT = path.resolve(__dirname, "..");
const IS_WIN = process.platform === "win32";

/** @typedef {{ cmd: string, prefixArgs?: string[], label?: string }} PyCandidate */

function pyCandidates() {
  /** @type {PyCandidate[]} */
  const list = [];
  const fromEnv = process.env.MOBIFLOW_PYTHON;
  if (fromEnv) {
    list.push({ cmd: fromEnv, label: "MOBIFLOW_PYTHON" });
  }
  if (IS_WIN) {
    // Prefer the Python launcher so we skip the Windows Store stub.
    list.push(
      { cmd: "py", prefixArgs: ["-3.12"], label: "py -3.12" },
      { cmd: "py", prefixArgs: ["-3.11"], label: "py -3.11" },
      { cmd: "py", prefixArgs: ["-3"], label: "py -3" },
      { cmd: "python3.12", label: "python3.12" },
      { cmd: "python3.11", label: "python3.11" },
      { cmd: "python", label: "python" },
      { cmd: "python3", label: "python3" }
    );
  } else {
    list.push(
      { cmd: "python3.12", label: "python3.12" },
      { cmd: "python3.11", label: "python3.11" },
      { cmd: "python3", label: "python3" },
      { cmd: "python", label: "python" }
    );
  }
  return list;
}

/**
 * Spawn without a shell so argv (especially ``-c``) is not mangled by cmd.exe.
 * @param {string} cmd
 * @param {string[]} args
 * @param {{ stdio?: any }} [opts]
 */
function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, {
    stdio: opts.stdio ?? "inherit",
    encoding: "utf8",
    windowsHide: true,
    env: process.env,
  });
}

/**
 * @param {PyCandidate} cand
 * @returns {{ major: number, minor: number } | null}
 */
function pythonVersion(cand) {
  // Avoid f-strings / nested quotes — Windows cmd historically mangled those
  // when shell:true was used; keep the probe trivial either way.
  const code =
    "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))";
  const prefix = cand.prefixArgs || [];
  const r = run(cand.cmd, [...prefix, "-c", code], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.error && r.error.code === "ENOENT") return null;
  if (r.status !== 0 || !r.stdout) return null;
  const text = r.stdout.toString().trim().split(/\r?\n/).pop() || "";
  const m = text.match(/^(\d+)\.(\d+)/);
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2]) };
}

/**
 * Reject the Microsoft Store alias that opens the Store instead of Python.
 * @param {string} exe
 */
function isWindowsStoreStub(exe) {
  if (!IS_WIN || !exe) return false;
  const n = exe.replace(/\//g, "\\").toLowerCase();
  return (
    n.includes("\\windowsapps\\") ||
    n.includes("\\microsoft\\windowsapps\\") ||
    n.endsWith("\\windowsapps\\python.exe") ||
    n.endsWith("\\windowsapps\\python3.exe")
  );
}

/**
 * @param {PyCandidate} cand
 * @returns {string | null}
 */
function resolveExecutable(cand) {
  const prefix = cand.prefixArgs || [];
  const r = run(cand.cmd, [...prefix, "-c", "import sys; print(sys.executable)"], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.status !== 0 || !r.stdout) return null;
  const exe = r.stdout.toString().trim().split(/\r?\n/).pop() || "";
  if (!exe || isWindowsStoreStub(exe)) return null;
  return exe;
}

function whichPython() {
  const tried = [];
  for (const cand of pyCandidates()) {
    const label = cand.label || cand.cmd;
    const ver = pythonVersion(cand);
    if (!ver) {
      tried.push(`${label} (not found / failed)`);
      continue;
    }
    if (ver.major < 3 || ver.minor < 11) {
      tried.push(`${label} (${ver.major}.${ver.minor} < 3.11)`);
      continue;
    }
    const exe = resolveExecutable(cand);
    if (!exe) {
      tried.push(`${label} (${ver.major}.${ver.minor}, stub or unusable)`);
      continue;
    }
    return exe;
  }
  whichPython._tried = tried;
  return null;
}

function moduleAvailable(py) {
  const r = run(py, ["-c", "import mobiflow"], {
    stdio: ["ignore", "ignore", "ignore"],
  });
  return r.status === 0;
}

/** Installed Python package version, or null if missing / unreadable. */
function installedVersion(py) {
  const code =
    "from importlib.metadata import version\n" +
    "print(version('mobiflow'))";
  const r = run(py, ["-c", code], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.status !== 0 || !r.stdout) return null;
  const ver = r.stdout.toString().trim().split(/\r?\n/).pop() || "";
  return ver || null;
}

function bundledRoot() {
  const pyproject = path.join(ROOT, "pyproject.toml");
  const pkgDir = path.join(ROOT, "src", "mobiflow");
  if (fs.existsSync(pyproject) && fs.existsSync(pkgDir)) return ROOT;
  return null;
}

function venvDir() {
  return process.env.MOBIFLOW_VENV || path.join(os.homedir(), ".mobiflow", "venv");
}

function venvPythonPath() {
  const dir = venvDir();
  return IS_WIN
    ? path.join(dir, "Scripts", "python.exe")
    : path.join(dir, "bin", "python");
}

/** Create ~/.mobiflow/venv with the discovered system Python (PEP 668 safe). */
function ensureVenv(systemPy) {
  const exe = venvPythonPath();
  if (fs.existsSync(exe)) {
    const ver = pythonVersion({ cmd: exe });
    if (ver && ver.major >= 3 && ver.minor >= 11) return exe;
  }
  console.error(`[mobiflow] Creating engine venv at ${venvDir()}`);
  fs.mkdirSync(path.dirname(venvDir()), { recursive: true });
  const r = run(systemPy, ["-m", "venv", venvDir()], { stdio: "inherit" });
  if (r.status !== 0 || !fs.existsSync(exe)) return null;
  return exe;
}

function pipInstall(py, spec) {
  console.error(`[mobiflow] Installing engine from ${spec}`);
  const r = run(py, ["-m", "pip", "install", "--upgrade", spec], {
    stdio: "inherit",
  });
  return r.status === 0;
}

function ensureMobiflow(py) {
  const current = installedVersion(py);
  if (current === VERSION) return true;
  if (current) {
    console.error(
      `[mobiflow] Engine is ${current}; need ${VERSION} — installing from this package…`
    );
  } else {
    console.error("[mobiflow] Installing engine from this npm package…");
  }

  const specs = [];
  if (process.env.MOBIFLOW_PIP_SPEC) {
    specs.push(process.env.MOBIFLOW_PIP_SPEC);
  }
  const bundled = bundledRoot();
  if (bundled) specs.push(bundled);

  if (!specs.length) {
    console.error(
      "[mobiflow] This npm package is missing pyproject.toml / src/mobiflow.\n" +
        "  Reinstall: npm install -g @qubiqlabs/mobiflow"
    );
    return false;
  }

  for (const spec of specs) {
    if (!pipInstall(py, spec)) continue;
    const got = installedVersion(py);
    if (got === VERSION) return true;
    if (moduleAvailable(py) && process.env.MOBIFLOW_PIP_SPEC && spec === process.env.MOBIFLOW_PIP_SPEC) {
      return true;
    }
  }
  return moduleAvailable(py);
}

function main(argv) {
  const systemPy = whichPython();
  if (!systemPy) {
    const tried = whichPython._tried || [];
    console.error(
      "[mobiflow] Python 3.11+ is required on PATH (the npm package ships the engine;\n" +
        "  it does not replace Python).\n" +
        "  https://www.python.org/downloads/\n" +
        "  Or set MOBIFLOW_PYTHON to your python.exe, e.g.\n" +
        "    set MOBIFLOW_PYTHON=C:\\Users\\You\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
    );
    if (tried.length) {
      console.error("  Tried: " + tried.join("; "));
    }
    process.exit(1);
  }

  const py = ensureVenv(systemPy);
  if (!py) {
    console.error(
      `[mobiflow] Could not create a venv with "${systemPy}".\n` +
        `  Try: "${systemPy}" -m venv "${venvDir()}"`
    );
    process.exit(1);
  }

  if (!ensureMobiflow(py)) {
    console.error(
      "[mobiflow] Could not install the engine from this npm package.\n" +
        `  Try: "${py}" -m pip install --upgrade "${ROOT}"`
    );
    process.exit(1);
  }

  const r = run(py, ["-m", "mobiflow", ...argv], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

main(process.argv.slice(2));
