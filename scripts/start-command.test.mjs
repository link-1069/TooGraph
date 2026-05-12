import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("root package exposes npm start as the formal launcher without a dev alias", () => {
  const rootPackage = readJson(resolve(rootDir, "package.json"));

  assert.equal(rootPackage.scripts.start, "node scripts/start.mjs");
  assert.equal(Object.hasOwn(rootPackage.scripts, "dev"), false);
});

test("frontend package does not expose a separate vite dev launcher", () => {
  const frontendPackage = readJson(resolve(rootDir, "frontend", "package.json"));

  assert.equal(Object.hasOwn(frontendPackage.scripts, "dev"), false);
});

test("start launcher supports an explicit bind host for container deployment", () => {
  const startSource = readFileSync(resolve(rootDir, "scripts", "start.mjs"), "utf8");

  assert.match(startSource, /process\.env\.TOOGRAPH_HOST/);
  assert.match(startSource, /process\.env\.HOST/);
  assert.match(startSource, /const appBindHost =/);
  assert.match(startSource, /"--host",\s*appBindHost/);
  assert.match(startSource, /appPublicHost/);
});
