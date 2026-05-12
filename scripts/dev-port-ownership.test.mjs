import assert from "node:assert/strict";
import test from "node:test";

import { createPortReleasePlan } from "./dev-port-ownership.mjs";

test("kills descendants when a known TooGraph port owner process has already exited", () => {
  const plan = createPortReleasePlan({
    port: "8765",
    portPids: ["34000"],
    processInfos: [
      {
        pid: "32620",
        parentPid: "34000",
        name: "python.exe",
        commandLine:
          '"C:\\ProgramData\\miniconda3\\python.exe" "-c" "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=34000, pipe_handle=596)" "--multiprocessing-fork"',
      },
    ],
    context: {
      knownTooGraphPids: new Set(["34000"]),
      rootDir: "C:\\Users\\abyss\\TooGraph",
      backendDir: "C:\\Users\\abyss\\TooGraph\\backend",
      frontendDir: "C:\\Users\\abyss\\TooGraph\\frontend",
      backendPort: "8765",
      frontendPort: "3477",
    },
  });

  assert.deepEqual(plan.blockedOwners, []);
  assert.deepEqual(plan.killPids, ["32620"]);
});

test("kills a port owner when its launcher ancestor belongs to this checkout", () => {
  const plan = createPortReleasePlan({
    port: "3477",
    portPids: ["525747"],
    processInfos: [
      {
        pid: "525627",
        parentPid: "1",
        name: "node",
        commandLine: "node /home/abyss/TooGraph/scripts/start.mjs",
      },
      {
        pid: "525747",
        parentPid: "525627",
        name: "python",
        commandLine: "/home/abyss/miniconda3/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 3477",
      },
    ],
    context: {
      knownTooGraphPids: new Set(),
      rootDir: "/home/abyss/TooGraph",
      backendDir: "/home/abyss/TooGraph/backend",
      frontendDir: "/home/abyss/TooGraph/frontend",
      backendPort: "3477",
      frontendPort: "3477",
    },
  });

  assert.deepEqual(plan.blockedOwners, []);
  assert.deepEqual(plan.killPids, ["525747"]);
});

test("kills a port owner when its working directory belongs to this checkout", () => {
  const plan = createPortReleasePlan({
    port: "3477",
    portPids: ["525747"],
    processInfos: [
      {
        pid: "525747",
        parentPid: "525627",
        name: "python",
        cwd: "/home/abyss/TooGraph/backend",
        commandLine: "/home/abyss/miniconda3/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 3477",
      },
    ],
    context: {
      knownTooGraphPids: new Set(),
      rootDir: "/home/abyss/TooGraph",
      backendDir: "/home/abyss/TooGraph/backend",
      frontendDir: "/home/abyss/TooGraph/frontend",
      backendPort: "3477",
      frontendPort: "3477",
    },
  });

  assert.deepEqual(plan.blockedOwners, []);
  assert.deepEqual(plan.killPids, ["525747"]);
});

test("blocks unknown port owners and includes process details for the user", () => {
  const plan = createPortReleasePlan({
    port: "8765",
    portPids: ["22222"],
    processInfos: [
      {
        pid: "22222",
        parentPid: "100",
        name: "python.exe",
        executablePath: "C:\\OtherApp\\python.exe",
        commandLine: '"C:\\OtherApp\\python.exe" -m uvicorn other.main:app --port 8765',
      },
    ],
    context: {
      knownTooGraphPids: new Set(),
      rootDir: "C:\\Users\\abyss\\TooGraph",
      backendDir: "C:\\Users\\abyss\\TooGraph\\backend",
      frontendDir: "C:\\Users\\abyss\\TooGraph\\frontend",
      backendPort: "8765",
      frontendPort: "3477",
    },
  });

  assert.deepEqual(plan.killPids, []);
  assert.equal(plan.blockedOwners.length, 1);
  assert.match(plan.blockedOwners[0], /PID 22222/);
  assert.match(plan.blockedOwners[0], /OtherApp/);
});

test("blocks lookalike dev servers that are not tied to this checkout", () => {
  const context = {
    knownTooGraphPids: new Set(),
    rootDir: "C:\\Users\\abyss\\TooGraph",
    backendDir: "C:\\Users\\abyss\\TooGraph\\backend",
    frontendDir: "C:\\Users\\abyss\\TooGraph\\frontend",
    backendPort: "8765",
    frontendPort: "3477",
  };

  const backendPlan = createPortReleasePlan({
    port: "8765",
    portPids: ["11111"],
    processInfos: [
      {
        pid: "11111",
        parentPid: "100",
        name: "python.exe",
        executablePath: "C:\\OtherCheckout\\python.exe",
        commandLine: '"C:\\OtherCheckout\\python.exe" -m uvicorn app.main:app --port 8765',
      },
    ],
    context,
  });
  const frontendPlan = createPortReleasePlan({
    port: "3477",
    portPids: ["33333"],
    processInfos: [
      {
        pid: "33333",
        parentPid: "100",
        name: "node.exe",
        executablePath: "C:\\Program Files\\nodejs\\node.exe",
        commandLine: '"node" "C:\\OtherCheckout\\frontend\\node_modules\\vite\\bin\\vite.js" --port 3477',
      },
    ],
    context,
  });

  assert.deepEqual(backendPlan.killPids, []);
  assert.equal(backendPlan.blockedOwners.length, 1);
  assert.deepEqual(frontendPlan.killPids, []);
  assert.equal(frontendPlan.blockedOwners.length, 1);
});
