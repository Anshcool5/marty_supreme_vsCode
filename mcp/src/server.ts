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

type GameId = "pong" | "tetris" | "blackjack" | "slots";
type GameDisplayName = "Pong" | "Tetris" | "Blackjack" | "Slots";
type LaunchResult = LaunchPongResult;
type StatusResult = PongStatusResult;
type StopResult = StopPongResult;

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, "..", "..");
const pongScriptPath = path.join(repoRoot, "python", "games", "hand_server.py");
const tetrisScriptPath = path.join(repoRoot, "python", "games", "tetris.py");
const blackjackScriptPath = path.join(repoRoot, "python", "games", "blackjack.py");
const slotsScriptPath = path.join(repoRoot, "python", "games", "slot_machine.py");
const venvPythonPath = path.join(repoRoot, "python", "venv", "bin", "python");

const activeProcesses: Record<GameId, ChildProcess | null> = {
  pong: null,
  tetris: null,
  blackjack: null,
  slots: null,
};

const gameConfigs: Record<
  GameId,
  {
    displayName: GameDisplayName;
    scriptPath: string;
    baseArgs?: string[];
  }
> = {
  pong: {
    displayName: "Pong",
    scriptPath: pongScriptPath,
    baseArgs: ["--run-pong"],
  },
  tetris: {
    displayName: "Tetris",
    scriptPath: tetrisScriptPath,
  },
  blackjack: {
    displayName: "Blackjack",
    scriptPath: blackjackScriptPath,
  },
  slots: {
    displayName: "Slots",
    scriptPath: slotsScriptPath,
  },
};

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

async function resolvePythonExecutable(): Promise<"python3" | string> {
  if (await fileExists(venvPythonPath)) {
    return venvPythonPath;
  }
  return "python3";
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
  if (isProcessRunning(activeProcesses.pong)) {
    return {
      status: "already_running",
      message: "Pong is already running.",
      pid: activeProcesses.pong.pid,
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
      activeProcesses.pong = null;
    });

    activeProcesses.pong = child;
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
  if (isProcessRunning(activeProcesses.pong)) {
    return { status: "running", pid: activeProcesses.pong.pid };
  }
  return { status: "not_running" };
}

function stopPong(force: boolean): StopPongResult {
  if (!isProcessRunning(activeProcesses.pong)) {
    return {
      status: "not_running",
      message: "Pong is not running.",
    };
  }

  const signal = force ? "SIGKILL" : "SIGTERM";
  const stopped = activeProcesses.pong.kill(signal);
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

async function launchGame(
  gameId: GameId,
  extraArgs: string[] = []
): Promise<LaunchResult> {
  const config = gameConfigs[gameId];
  const activeProcess = activeProcesses[gameId];

  if (isProcessRunning(activeProcess)) {
    return {
      status: "already_running",
      message: `${config.displayName} is already running.`,
      pid: activeProcess.pid,
    };
  }

  if (!(await fileExists(config.scriptPath))) {
    return {
      status: "error",
      message: `${config.displayName} script not found at ${config.scriptPath}`,
    };
  }

  const pythonExecutable = await resolvePythonExecutable();
  const args = [...(config.baseArgs ?? []), ...extraArgs];
  const scriptAndArgs = [config.scriptPath, ...args];
  const gameTag = gameId;

  try {
    const child = spawn(pythonExecutable, scriptAndArgs, {
      cwd: repoRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout?.on("data", (data: Buffer) => {
      log(`${gameTag} stdout: ${data.toString().trim()}`);
    });
    child.stderr?.on("data", (data: Buffer) => {
      log(`${gameTag} stderr: ${data.toString().trim()}`);
    });
    child.on("error", (error) => {
      log(`${gameTag} process error: ${error.message}`);
    });
    child.on("exit", (code, signal) => {
      log(`${gameTag} exited with code=${code} signal=${signal}`);
      activeProcesses[gameId] = null;
    });

    activeProcesses[gameId] = child;
    log(
      `launch_${gameTag} -> python="${pythonExecutable}" pid=${
        child.pid ?? "unknown"
      } args=${JSON.stringify(args)}`
    );

    return {
      status: "launched",
      message: `${config.displayName} launched successfully.`,
      pid: child.pid,
    };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown launch error";
    log(`launch_${gameTag} failed: ${message}`);
    return {
      status: "error",
      message: `Failed to launch ${config.displayName}: ${message}`,
    };
  }
}

function gameStatus(gameId: GameId): StatusResult {
  const activeProcess = activeProcesses[gameId];
  if (isProcessRunning(activeProcess)) {
    return { status: "running", pid: activeProcess.pid };
  }
  return { status: "not_running" };
}

function stopGame(gameId: GameId, force: boolean): StopResult {
  const config = gameConfigs[gameId];
  const activeProcess = activeProcesses[gameId];
  if (!isProcessRunning(activeProcess)) {
    return {
      status: "not_running",
      message: `${config.displayName} is not running.`,
    };
  }

  const signal = force ? "SIGKILL" : "SIGTERM";
  const stopped = activeProcess.kill(signal);
  log(`stop_${gameId} -> signal=${signal} success=${stopped}`);

  if (!stopped) {
    return {
      status: "error",
      message: `Failed to signal ${config.displayName} process.`,
    };
  }

  return {
    status: "stopped",
    message: `${config.displayName} stop signal sent (${signal}).`,
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
        name: "launch_tetris",
        description:
          "Launch Marty Supreme Tetris if not already running. Returns launch status and pid when available.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "tetris_status",
        description: "Get current Tetris process status and pid.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "stop_tetris",
        description:
          "Stop the currently running Tetris process, if any. Optional force flag sends SIGKILL.",
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
        name: "launch_blackjack",
        description:
          "Launch Marty Supreme Blackjack if not already running. Returns launch status and pid when available.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "blackjack_status",
        description: "Get current Blackjack process status and pid.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "stop_blackjack",
        description:
          "Stop the currently running Blackjack process, if any. Optional force flag sends SIGKILL.",
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
        name: "launch_slots",
        description:
          "Launch Marty Supreme Slots if not already running. Returns launch status and pid when available.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "slots_status",
        description: "Get current Slots process status and pid.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
      {
        name: "stop_slots",
        description:
          "Stop the currently running Slots process, if any. Optional force flag sends SIGKILL.",
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
    case "launch_tetris": {
      const result = await launchGame("tetris");
      return toolResponse(result, result.status === "error");
    }
    case "tetris_status": {
      const result = gameStatus("tetris");
      return toolResponse(result);
    }
    case "stop_tetris": {
      const force = parseBooleanArg(args?.force, false);
      const result = stopGame("tetris", force);
      return toolResponse(result, result.status === "error");
    }
    case "launch_blackjack": {
      const result = await launchGame("blackjack");
      return toolResponse(result, result.status === "error");
    }
    case "blackjack_status": {
      const result = gameStatus("blackjack");
      return toolResponse(result);
    }
    case "stop_blackjack": {
      const force = parseBooleanArg(args?.force, false);
      const result = stopGame("blackjack", force);
      return toolResponse(result, result.status === "error");
    }
    case "launch_slots": {
      const result = await launchGame("slots");
      return toolResponse(result, result.status === "error");
    }
    case "slots_status": {
      const result = gameStatus("slots");
      return toolResponse(result);
    }
    case "stop_slots": {
      const force = parseBooleanArg(args?.force, false);
      const result = stopGame("slots", force);
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
  (Object.keys(activeProcesses) as GameId[]).forEach((gameId) => {
    const activeProcess = activeProcesses[gameId];
    if (isProcessRunning(activeProcess)) {
      activeProcess.kill("SIGTERM");
    }
  });
  process.exit(0);
});

process.on("SIGTERM", () => {
  (Object.keys(activeProcesses) as GameId[]).forEach((gameId) => {
    const activeProcess = activeProcesses[gameId];
    if (isProcessRunning(activeProcess)) {
      activeProcess.kill("SIGTERM");
    }
  });
  process.exit(0);
});

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  log(`fatal: ${message}`);
  process.exit(1);
});
