import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(currentDirectory, "SettingsPage.vue"), "utf8");

test("SettingsPage exposes a persisted developer mode toggle", () => {
  assert.match(pageSource, /settings\.developerOptions/);
  assert.match(pageSource, /settings\.developerMode/);
  assert.match(pageSource, /settings\.developerModeHelp/);
  assert.match(pageSource, /ElSwitch/);
  assert.match(pageSource, /developer_mode/);
  assert.match(pageSource, /ui_preferences/);
});
