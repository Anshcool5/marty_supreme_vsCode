# Marty Supreme MCP Server

MCP server that exposes agent tools for game lifecycle control:

- `launch_pong(showPreview?: boolean)`
- `pong_status()`
- `stop_pong(force?: boolean)`
- `launch_ninja(showPreview?: boolean, cameraIndex?: number)`
- `ninja_status()`
- `stop_ninja(force?: boolean)`

This is additive to the VS Code extension command/chat flows. It does not replace:

- `marty-supreme.runPong`
- `@marty` chat participant

## Prerequisites

- macOS or Linux shell
- Node.js 18+
- Python environment with game dependencies installed
- Pong script present at `python/games/hand_server.py`

## Install and Build

From repo root:

```bash
npm --prefix mcp install
npm run mcp:build
```

## Run Standalone

```bash
npm run mcp:start
```

For development:

```bash
npm run mcp:dev
```

## Codex/Agent MCP Config

Use the sample config in `mcp/codex.mcp.example.json` and point your client to run:

- `node`
- args: `["/absolute/path/to/marty_supreme_vsCode/mcp/dist/server.js"]`

Set approvals to prompt for mutating tools (`launch_*`, `stop_*`) and allow status tools without prompt if your client supports per-tool policies.

## Tool Contracts

### `launch_pong`

Input:

```json
{ "showPreview": true }
```

Output:

```json
{ "status": "launched|already_running|error", "message": "string", "pid": 12345 }
```

### `pong_status`

Input:

```json
{}
```

Output:

```json
{ "status": "running|not_running", "pid": 12345 }
```

### `stop_pong`

Input:

```json
{ "force": false }
```

Output:

```json
{ "status": "stopped|not_running|error", "message": "string" }
```

### `launch_ninja`

Input:

```json
{ "showPreview": false, "cameraIndex": 0 }
```

Output:

```json
{ "status": "launched|already_running|error", "message": "string", "pid": 12345 }
```

### `ninja_status`

Input:

```json
{}
```

Output:

```json
{ "status": "running|not_running", "pid": 12345 }
```

### `stop_ninja`

Input:

```json
{ "force": false }
```

Output:

```json
{ "status": "stopped|not_running|error", "message": "string" }
```

## Troubleshooting

- Camera permission denied:
  - Grant camera access to VS Code / terminal host process.
- Missing Python deps (`mediapipe`, `opencv-python`, `pygame`):
  - Install from your project venv.
- Script not found:
  - Verify `python/games/hand_server.py` exists in this repo.
- Ninja script not found:
  - Verify `python/games/ninja.py` exists in this repo.
- Tool returns `already_running`:
  - Use `*_status` and `stop_*` to manage lifecycle.

Server logs are written to `stderr` with the prefix `[marty-mcp]`.
