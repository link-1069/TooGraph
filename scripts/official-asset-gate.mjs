import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { delimiter, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const OFFICIAL_TEMPLATE_PREFIX = "graph_template/official/";
const OFFICIAL_ACTION_PREFIX = "action/official/";
const OFFICIAL_TOOL_PREFIX = "tool/official/";
const ALLOWED_VERIFICATION_COMMANDS = new Set(["python", "node", "npm"]);

const GIT_DIFF_CHECK = {
  name: "diff whitespace check",
  command: "git",
  args: ["diff", "--check"],
};

const TEMPLATE_GATE = {
  name: "official template gate",
  command: "python",
  args: [
    "-m",
    "unittest",
    "backend.tests.test_template_layouts",
    "backend.tests.test_evaluator_official_seed",
  ],
};

const ACTION_GATE = {
  name: "official action gate",
  command: "python",
  args: [
    "-m",
    "unittest",
    "backend.tests.test_action_manifest_contract",
    "backend.tests.test_backend_action_package_naming",
    "backend.tests.test_node_system_validator_actions",
  ],
};

const TOOL_GATE = {
  name: "official tool gate",
  command: "python",
  args: [
    "-m",
    "unittest",
    "backend.tests.test_tool_catalog_routes",
    "backend.tests.test_node_system_validator_tools",
    "backend.tests.test_tool_node_runtime",
    "backend.tests.test_official_tool_eval_bindings",
  ],
};

export function resolveOfficialAssetGatePlan({ changedPaths = [] } = {}) {
  const normalizedPaths = changedPaths.map(normalizePath).filter(Boolean);
  const changedAssetKinds = [];
  const commands = [GIT_DIFF_CHECK];
  const templateEvalSuiteIds = resolveChangedTemplateEvalSuiteIds(normalizedPaths);
  const changedActionKeys = resolveChangedPackageKeys(normalizedPaths, OFFICIAL_ACTION_PREFIX);
  const changedToolKeys = resolveChangedPackageKeys(normalizedPaths, OFFICIAL_TOOL_PREFIX);

  if (normalizedPaths.some((path) => path.startsWith(OFFICIAL_TEMPLATE_PREFIX))) {
    changedAssetKinds.push("official_template");
    appendCommand(commands, TEMPLATE_GATE);
    for (const suiteId of templateEvalSuiteIds) {
      appendCommand(commands, {
        name: `official eval suite gate: ${suiteId}`,
        command: "python",
        args: ["scripts/official_eval_suite_gate.py", suiteId],
      });
    }
  }
  if (normalizedPaths.some((path) => path.startsWith(OFFICIAL_ACTION_PREFIX))) {
    changedAssetKinds.push("official_action");
    appendCommand(commands, ACTION_GATE);
    for (const moduleName of resolvePackageSpecificTestModules(changedActionKeys, "action")) {
      appendCommand(commands, {
        name: `official action package test: ${moduleName}`,
        command: "python",
        args: ["-m", "unittest", moduleName],
      });
    }
    for (const command of resolveManifestVerificationCommands(changedActionKeys, OFFICIAL_ACTION_PREFIX, "action.json")) {
      appendCommand(commands, command);
    }
    for (const suiteId of resolveManifestEvalSuiteIds(changedActionKeys, OFFICIAL_ACTION_PREFIX, "action.json")) {
      appendCommand(commands, officialEvalSuiteCommand(suiteId));
    }
  }
  if (normalizedPaths.some((path) => path.startsWith(OFFICIAL_TOOL_PREFIX))) {
    changedAssetKinds.push("official_tool");
    appendCommand(commands, TOOL_GATE);
    for (const moduleName of resolvePackageSpecificTestModules(changedToolKeys, "tool")) {
      appendCommand(commands, {
        name: `official tool package test: ${moduleName}`,
        command: "python",
        args: ["-m", "unittest", moduleName],
      });
    }
    for (const command of resolveManifestVerificationCommands(changedToolKeys, OFFICIAL_TOOL_PREFIX, "tool.json")) {
      appendCommand(commands, command);
    }
    for (const suiteId of resolveManifestEvalSuiteIds(changedToolKeys, OFFICIAL_TOOL_PREFIX, "tool.json")) {
      appendCommand(commands, officialEvalSuiteCommand(suiteId));
    }
  }

  return {
    changedAssetKinds,
    commands,
  };
}

function officialEvalSuiteCommand(suiteId) {
  return {
    name: `official eval suite gate: ${suiteId}`,
    command: "python",
    args: ["scripts/official_eval_suite_gate.py", suiteId],
  };
}

function appendCommand(commands, command) {
  const signature = commandSignature(command);
  if (commands.some((existing) => commandSignature(existing) === signature)) {
    return;
  }
  commands.push(command);
}

function commandSignature(command) {
  return `${command.command}\u0000${command.args.join("\u0000")}`;
}

function resolveChangedPackageKeys(changedPaths, prefix) {
  return uniqueTextList(
    changedPaths
      .filter((path) => path.startsWith(prefix))
      .map((path) => path.slice(prefix.length).split("/")[0])
      .filter(Boolean),
  );
}

function resolvePackageSpecificTestModules(packageKeys, kind) {
  const modules = [];
  for (const packageKey of packageKeys) {
    for (const moduleName of packageTestModuleCandidates(packageKey, kind)) {
      if (testModuleExists(moduleName)) {
        modules.push(moduleName);
        break;
      }
    }
  }
  return uniqueTextList(modules);
}

function packageTestModuleCandidates(packageKey, kind) {
  const suffix = kind === "tool" ? "tool" : "action";
  return [
    `backend.tests.test_${packageKey}_${suffix}`,
    `backend.tests.test_${packageKey}`,
  ];
}

function testModuleExists(moduleName) {
  const relativePath = `${moduleName.replaceAll(".", "/")}.py`;
  return existsSync(relativePath);
}

function resolveManifestVerificationCommands(packageKeys, prefix, manifestFileName) {
  return packageKeys.flatMap((packageKey) => {
    const manifestPath = `${prefix}${packageKey}/${manifestFileName}`;
    if (!existsSync(manifestPath)) {
      return [];
    }
    let payload;
    try {
      payload = JSON.parse(readFileSync(manifestPath, "utf8"));
    } catch {
      return [];
    }
    const verificationCommands = payload?.verificationCommands;
    if (!Array.isArray(verificationCommands)) {
      return [];
    }
    return verificationCommands.map((command, index) =>
      parseVerificationCommand(command, {
        packageKey,
        manifestPath,
        index,
      }),
    );
  });
}

function resolveManifestEvalSuiteIds(packageKeys, prefix, manifestFileName) {
  return uniqueTextList(
    packageKeys.flatMap((packageKey) => {
      const manifestPath = `${prefix}${packageKey}/${manifestFileName}`;
      if (!existsSync(manifestPath)) {
        return [];
      }
      let payload;
      try {
        payload = JSON.parse(readFileSync(manifestPath, "utf8"));
      } catch {
        return [];
      }
      const suites = payload?.verificationEvalSuites ?? payload?.verification_eval_suites;
      if (!Array.isArray(suites)) {
        return [];
      }
      return suites.map(normalizePath).filter(Boolean);
    }),
  );
}

function parseVerificationCommand(command, { packageKey, manifestPath, index }) {
  if (!command || typeof command !== "object" || Array.isArray(command)) {
    throw new Error(`Invalid verificationCommands[${index}] in ${manifestPath} for ${packageKey}.`);
  }
  const commandName = normalizeCommandName(command.command);
  if (!ALLOWED_VERIFICATION_COMMANDS.has(commandName)) {
    throw new Error(`Unsupported verification command '${command.command}' in ${manifestPath}.`);
  }
  const args = command.args;
  if (!Array.isArray(args) || !args.every((arg) => typeof arg === "string" && arg.trim())) {
    throw new Error(`verificationCommands[${index}].args must be a non-empty string array in ${manifestPath}.`);
  }
  return {
    name: String(command.name || `manifest verification: ${packageKey}`).trim(),
    command: commandName,
    args: args.map((arg) => arg.trim()),
  };
}

function normalizeCommandName(command) {
  return String(command || "").trim();
}

function resolveChangedTemplateEvalSuiteIds(changedPaths) {
  const templateIds = uniqueTextList(
    changedPaths
      .filter((path) => path.startsWith(OFFICIAL_TEMPLATE_PREFIX))
      .map((path) => path.slice(OFFICIAL_TEMPLATE_PREFIX.length).split("/")[0])
      .filter(Boolean),
  );
  return templateIds
    .map(readTemplateEvalSuiteId)
    .filter(Boolean);
}

function readTemplateEvalSuiteId(templateId) {
  const evalPath = `${OFFICIAL_TEMPLATE_PREFIX}${templateId}/eval_cases.json`;
  if (!existsSync(evalPath)) {
    return "";
  }
  try {
    const payload = JSON.parse(readFileSync(evalPath, "utf8"));
    return normalizePath(payload?.suite ?? payload?.suite_id);
  } catch {
    return "";
  }
}

function normalizePath(path) {
  return String(path || "").trim().replaceAll("\\", "/");
}

export function parseGitChangedPaths({ diffOutput = "", untrackedOutput = "" } = {}) {
  return uniqueTextList(
    `${diffOutput}\n${untrackedOutput}`
      .split(/\r?\n/)
      .map((line) => normalizePath(line))
      .filter(Boolean),
  );
}

function uniqueTextList(values) {
  const seen = new Set();
  return values.filter((value) => {
    if (!value || seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
}

function runGit(args) {
  const result = spawnSync("git", args, {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "Could not list changed files.");
  }
  return result.stdout;
}

function listChangedPathsFromGit() {
  return parseGitChangedPaths({
    diffOutput: runGit(["diff", "--name-only", "HEAD"]),
    untrackedOutput: runGit(["ls-files", "--others", "--exclude-standard"]),
  });
}

function runPlan(plan) {
  for (const command of plan.commands) {
    console.log(`\n> ${command.command} ${command.args.join(" ")}`);
    const result = spawnSync(command.command, command.args, {
      stdio: "inherit",
      env: createCommandEnvironment(process.env),
    });
    if (result.status !== 0) {
      return result.status ?? 1;
    }
  }
  return 0;
}

export function createCommandEnvironment(baseEnv = process.env) {
  const backendPath = resolve("backend");
  return {
    ...baseEnv,
    PYTHONPATH: [backendPath, baseEnv.PYTHONPATH].filter(Boolean).join(delimiter),
  };
}

function printPlan(plan) {
  if (plan.changedAssetKinds.length > 0) {
    console.log(`Official asset kinds: ${plan.changedAssetKinds.join(", ")}`);
  } else {
    console.log("Official asset kinds: none");
  }
  for (const command of plan.commands) {
    console.log(`${command.command} ${command.args.join(" ")}`);
  }
}

function main(argv) {
  const run = argv.includes("--run");
  const explicitPaths = argv.filter((arg) => arg !== "--run");
  const changedPaths = explicitPaths.length > 0 ? explicitPaths : listChangedPathsFromGit();
  const plan = resolveOfficialAssetGatePlan({ changedPaths });
  if (!run) {
    printPlan(plan);
    return 0;
  }
  return runPlan(plan);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
