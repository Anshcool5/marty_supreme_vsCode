import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  McpError,
  ErrorCode,
} from "@modelcontextprotocol/sdk/types.js";

type LaunchPongResult = {
  status: "launched" | "already_running" | "error";
  message: string;
  pid?: number;
};

type PongStatusResult = {
  status: "running" | "not_running";
  pid?: number;
};

type StopPongResult = {
  status: "stopped" | "not_running" | "error";
  message: string;
};

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, "..", "..");
const pongScriptPath = path.join(repoRoot, "python", "games", "hand_server.py");
const ninjaScriptPath = path.join(repoRoot, "python", "games", "ninja.py");
const venvPythonPath = path.join(repoRoot, "python", "venv", "bin", "python");

let activePongProcess: ChildProcess | null = null;
let activeNinjaProcess: ChildProcess | null = null;

const server = new Server(
  {
    name: "marty-supreme-pong-mcp",
    version: "0.0.1",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

function log(message: string): void {
  console.error(`[marty-mcp] ${message}`);
}

function isProcessRunning(process: ChildProcess | null): process is ChildProcess {
  return Boolean(process && process.exitCode === null && !process.killed);
}

function parseBooleanArg(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function resolvePythonExecutable(): Promise<string> {
  if (await fileExists(venvPythonPath)) {
    return venvPythonPath;
  }
  return "python";
}

function toolResponse(result: Record<string, unknown>, isError = false) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result),
      },
    ],
    structuredContent: result,
    isError,
  };
}

async function launchPong(showPreview: boolean): Promise<LaunchPongResult> {
  if (isProcessRunning(activePongProcess)) {
    return {
      status: "already_running",
      message: "Pong is already running.",
      pid: activePongProcess.pid,
    };
  }

  if (!(await fileExists(pongScriptPath))) {
    return {
      status: "error",
      message: `Pong script not found at ${pongScriptPath}`,
    };
  }

  const pythonExecutable = await resolvePythonExecutable();
  const args = [pongScriptPath, "--run-pong"];
  if (showPreview) {
    args.push("--show-preview");
  }

  try {
    const child = spawn(pythonExecutable, args, {
      cwd: repoRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout?.on("data", (data: Buffer) => {
      log(`pong stdout: ${data.toString().trim()}`);
    });
    child.stderr?.on("data", (data: Buffer) => {
      log(`pong stderr: ${data.toString().trim()}`);
    });
    child.on("error", (error) => {
      log(`pong process error: ${error.message}`);
    });
    child.on("exit", (code, signal) => {
      log(`pong exited with code=${code} signal=${signal}`);
      activePongProcess = null;
    });

    activePongProcess = child;
    log(
      `launch_pong -> python="${pythonExecutable}" pid=${
        child.pid ?? "unknown"
      } showPreview=${showPreview}`
    );

    return {
      status: "launched",
      message: "Pong launched successfully.",
      pid: child.pid,
    };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown launch error";
    log(`launch_pong failed: ${message}`);
    return {
      status: "error",
      message: `Failed to launch Pong: ${message}`,
    };
  }
}

function pongStatus(): PongStatusResult {
  if (isProcessRunning(activePongProcess)) {
    return { status: "running", pid: activePongProcess.pid };
  }
  return { status: "not_running" };
}

function stopPong(force: boolean): StopPongResult {
  if (!isProcessRunning(activePongProcess)) {
    return {
      status: "not_running",
      message: "Pong is not running.",
    };
  }

  const signal = force ? "SIGKILL" : "SIGTERM";
  const stopped = activePongProcess.kill(signal);
  log(`stop_pong -> signal=${signal} success=${stopped}`);

  if (!stopped) {
    return {
      status: "error",
      message: "Failed to signal Pong process.",
    };
  }

  return {
    status: "stopped",
    message: `Pong stop signal sent (${signal}).`,
  };
}

async function launchNinja(
  showPreview: boolean,
  cameraIndex: number
): Promise<LaunchPongResult> {
  if (isProcessRunning(activeNinjaProcess)) {
    return {
      status: "already_running",
      message: "Ninja is already running.",
      pid: activeNinjaProcess.pid,
    };
  }

  if (!(await fileExists(ninjaScriptPath))) {
    return {
      status: "error",
      message: `Ninja script not found at ${ninjaScriptPath}`,
    };
  }

  const pythonExecutable = await resolvePythonExecutable();
  const args = [ninjaScriptPath, "--camera-index", String(cameraIndex)];
  if (showPreview) {
    args.push("--show-preview");
  }

  try {
    const child = spawn(pythonExecutable, args, {
      cwd: repoRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout?.on("data", (data: Buffer) => {
      log(`ninja stdout: ${data.toString().trim()}`);
    });
    child.stderr?.on("data", (data: Buffer) => {
      log(`ninja stderr: ${data.toString().trim()}`);
    });
    child.on("error", (error) => {
      log(`ninja process error: ${error.message}`);
    });
    child.on("exit", (code, signal) => {
      log(`ninja exited with code=${code} signal=${signal}`);
      activeNinjaProcess = null;
    });

    activeNinjaProcess = child;
    log(
      `launch_ninja -> python="${pythonExecutable}" pid=${
        child.pid ?? "unknown"
      } showPreview=${showPreview} cameraIndex=${cameraIndex}`
    );

    return {
      status: "launched",
      message: "Ninja launched successfully.",
      pid: child.pid,
    };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown launch error";
    log(`launch_ninja failed: ${message}`);
    return {
      status: "error",
      message: `Failed to launch Ninja: ${message}`,
    };
  }
}

function ninjaStatus(): PongStatusResult {
  if (isProcessRunning(activeNinjaProcess)) {
    return { status: "running", pid: activeNinjaProcess.pid };
  }
  return { status: "not_running" };
}

function stopNinja(force: boolean): StopPongResult {
  if (!isProcessRunning(activeNinjaProcess)) {
    return {
      status: "not_running",
      message: "Ninja is not running.",
    };
  }

  const signal = force ? "SIGKILL" : "SIGTERM";
  const stopped = activeNinjaProcess.kill(signal);
  log(`stop_ninja -> signal=${signal} success=${stopped}`);

  if (!stopped) {
    return {
      status: "error",
      message: "Failed to signal Ninja process.",
    };
  }

  return {
    status: "stopped",
    message: `Ninja stop signal sent (${signal}).`,
  };
}

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "launch_pong",
        description:
          "Launch Marty Supreme Pong if not already running. Returns launch status and pid when available.",
        inputSchema: {
          type: "object",
          properties: {
            showPreview: {
              type: "boolean",
              description:
                "Whether to show the OpenCV camera preview window. Defaults to true.",
            },
          },
          additionalProperties: false,
        },
      },
      {
        name: "pong_status",
        description: "Get current Pong process status and pid.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "stop_pong",
        description:
          "Stop the currently running Pong process, if any. Optional force flag sends SIGKILL.",
        inputSchema: {
          type: "object",
          properties: {
            force: {
              type: "boolean",
              description:
                "When true, sends SIGKILL instead of SIGTERM. Defaults to false.",
            },
          },
          additionalProperties: false,
        },
      },
      {
        name: "launch_ninja",
        description:
          "Launch Marty Supreme Fruit Slayer Ninja if not already running. Returns launch status and pid when available.",
        inputSchema: {
          type: "object",
          properties: {
            showPreview: {
              type: "boolean",
              description:
                "Whether to show the debug camera preview window. Defaults to false.",
            },
            cameraIndex: {
              type: "number",
              description:
                "Camera index passed to ninja.py --camera-index. Defaults to 0.",
            },
          },
          additionalProperties: false,
        },
      },
      {
        name: "ninja_status",
        description: "Get current Ninja process status and pid.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "stop_ninja",
        description:
          "Stop the currently running Ninja process, if any. Optional force flag sends SIGKILL.",
        inputSchema: {
          type: "object",
          properties: {
            force: {
              type: "boolean",
              description:
                "When true, sends SIGKILL instead of SIGTERM. Defaults to false.",
            },
          },
          additionalProperties: false,
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request: any) => {
  const { name, arguments: args } = request.params;
  log(`tool invoked: ${name}`);

  switch (name) {
    case "launch_pong": {
      const showPreview = parseBooleanArg(args?.showPreview, true);
      const result = await launchPong(showPreview);
      return toolResponse(result, result.status === "error");
    }
    case "pong_status": {
      const result = pongStatus();
      return toolResponse(result);
    }
    case "stop_pong": {
      const force = parseBooleanArg(args?.force, false);
      const result = stopPong(force);
      return toolResponse(result, result.status === "error");
    }
    case "launch_ninja": {
      const showPreview = parseBooleanArg(args?.showPreview, false);
      const cameraIndex =
        typeof args?.cameraIndex === "number" ? Math.max(0, Math.floor(args.cameraIndex)) : 0;
      const result = await launchNinja(showPreview, cameraIndex);
      return toolResponse(result, result.status === "error");
    }
    case "ninja_status": {
      const result = ninjaStatus();
      return toolResponse(result);
    }
    case "stop_ninja": {
      const force = parseBooleanArg(args?.force, false);
      const result = stopNinja(force);
      return toolResponse(result, result.status === "error");
    }
    default:
      throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
  }
});

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("MCP server connected via stdio");
}

process.on("SIGINT", () => {
  if (isProcessRunning(activePongProcess)) {
    activePongProcess.kill("SIGTERM");
  }
  if (isProcessRunning(activeNinjaProcess)) {
    activeNinjaProcess.kill("SIGTERM");
  }
  process.exit(0);
});

process.on("SIGTERM", () => {
  if (isProcessRunning(activePongProcess)) {
    activePongProcess.kill("SIGTERM");
  }
  if (isProcessRunning(activeNinjaProcess)) {
    activeNinjaProcess.kill("SIGTERM");
  }
  process.exit(0);
});

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  log(`fatal: ${message}`);
  process.exit(1);
});
