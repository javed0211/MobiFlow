#!/usr/bin/env node
/**
 * npm bin wrapper for the Python MobiFlow CLI.
 * Resolves: PATH mobiflow → python -m mobiflow → pip install → retry.
 *
 * Windows note: never run ``python -c "…"`` through ``cmd.exe`` (shell:true) —
 * quoting breaks and a real 3.12 install looks like “no Python 3.11+”.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PKG = require("../package.json");
const VERSION = PKG.version || "0.1.0";
const REPO = "https://github.com/javed0211/MobiFlow.git";
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

function pathLookup(binName) {
  // Use where.exe explicitly — ``where`` with shell can behave oddly.
  const cmd = IS_WIN ? "where.exe" : "which";
  return run(cmd, [binName], { stdio: ["ignore", "pipe", "ignore"] });
}

function main(argv) {
  const py = whichPython();
  if (!py) {
    const tried = whichPython._tried || [];
    console.error(
      "[mobiflow] Python 3.11+ is required on PATH.\n" +
        "  https://www.python.org/downloads/\n" +
        "  Or set MOBIFLOW_PYTHON to your python.exe, e.g.\n" +
        '    set MOBIFLOW_PYTHON=C:\\Users\\You\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\n' +
        "  Or: py -3.12 -m pip install mobiflow && py -3.12 -m mobiflow --help"
    );
    if (tried.length) {
      console.error("  Tried: " + tried.join("; "));
    }
    process.exit(1);
  }

  // Prefer an already-installed console script on PATH (avoid recursion).
  const self = path.resolve(__filename);
  const onPath = pathLookup("mobiflow");
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
      if (resolved.includes(`${path.sep}@qubiqlabs${path.sep}mobiflow${path.sep}`)) {
        continue;
      }
      if (resolved.includes(`${path.sep}mobiflow${path.sep}bin${path.sep}`)) {
        continue;
      }
      // Console scripts on Windows are often .cmd — shell helps those only.
      const r = spawnSync(bin, argv, {
        stdio: "inherit",
        windowsHide: true,
        env: process.env,
        shell: IS_WIN && /\.(cmd|bat)$/i.test(bin),
      });
      process.exit(r.status ?? 1);
    }
  }

  if (!ensureMobiflow(py)) {
    console.error(
      "[mobiflow] Could not install the Python package.\n" +
        `  Try: "${py}" -m pip install "git+${REPO}@main"\n` +
        `  Or:  "${py}" -m pip install mobiflow`
    );
    process.exit(1);
  }

  const r = run(py, ["-m", "mobiflow", ...argv], { stdio: "inherit" });
  process.exit(r.status ?? 1);
}

main(process.argv.slice(2));
