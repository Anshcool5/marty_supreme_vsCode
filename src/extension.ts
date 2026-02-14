import * as vscode from 'vscode';
import { PythonProcessManager } from './python/processManager';
import { resolvePythonInterpreter } from './python/interpreter';
import * as path from 'path';
import { ChildProcess, spawn } from 'child_process';
import * as net from 'net';

class ThinkingPingPongController implements vscode.Disposable {
  private panel: vscode.WebviewPanel | undefined;
  private pythonProcess: ChildProcess | undefined;
  private handServerPort = 8765;
  private debugPreviewEnabled = false;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly output: vscode.OutputChannel
  ) {}

  async startThinking(reason: string, options?: { debugPreview?: boolean }): Promise<void> {
    this.debugPreviewEnabled = Boolean(options?.debugPreview);
    await this.ensurePort();
    this.ensureWebview();
    await this.startHandServer();
    this.postState({ thinking: true, reason, port: this.handServerPort });
    this.panel?.reveal(vscode.ViewColumn.Beside, true);
  }

  stopThinking(): void {
    this.postState({ thinking: false });
    this.stopHandServer();
  }

  async restartHandServer(): Promise<void> {
    this.stopHandServer();
    await this.startHandServer();
    this.postState({ thinking: true, reason: 'manual_restart', port: this.handServerPort });
  }

  dispose(): void {
    this.stopHandServer();
    this.panel?.dispose();
  }

  private async ensurePort(): Promise<void> {
    const preferred = 8765;
    this.handServerPort = await this.findOpenPort(preferred);
  }

  private findOpenPort(startPort: number): Promise<number> {
    return new Promise((resolve) => {
      const tryPort = (port: number) => {
        const server = net.createServer();
        server.once('error', () => tryPort(port + 1));
        server.once('listening', () => {
          server.close(() => resolve(port));
        });
        server.listen(port, '127.0.0.1');
      };
      tryPort(startPort);
    });
  }

  private ensureWebview(): void {
    if (this.panel) {
      return;
    }

    this.panel = vscode.window.createWebviewPanel(
      'martySupremeThinkingPingPong',
      'Marty Supreme Ping Pong',
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      { enableScripts: true, retainContextWhenHidden: true }
    );

    this.panel.webview.html = this.getWebviewHtml();

    this.panel.webview.onDidReceiveMessage(
      async (message: any) => {
        if (message?.type === 'restart-server') {
          await this.restartHandServer();
        }
      },
      undefined,
      this.context.subscriptions
    );

    this.panel.onDidDispose(() => {
      this.panel = undefined;
    });
  }

  private postState(payload: { thinking: boolean; reason?: string; port?: number }): void {
    this.panel?.webview.postMessage({ type: 'state', ...payload });
  }

  private async startHandServer(): Promise<void> {
    if (this.pythonProcess) {
      return;
    }

    const pythonBin = await resolvePythonInterpreter(this.context, this.output);
    const scriptPath = path.join(this.context.extensionPath, 'python', 'games', 'hand_server.py');
    const args = [scriptPath, '--port', String(this.handServerPort)];
    if (this.debugPreviewEnabled) {
      args.push('--show-preview');
    }

    this.output.appendLine(`Starting hand server: ${pythonBin} ${args.join(' ')}`);
    this.pythonProcess = spawn(pythonBin, args, {
      cwd: this.context.extensionPath,
      env: { ...process.env },
    });

    this.pythonProcess.stdout?.on('data', (data: Buffer) => {
      this.output.appendLine(`[hand_server] ${data.toString().trimEnd()}`);
    });

    this.pythonProcess.stderr?.on('data', (data: Buffer) => {
      this.output.appendLine(`[hand_server:stderr] ${data.toString().trimEnd()}`);
    });

    this.pythonProcess.on('exit', (code, signal) => {
      this.output.appendLine(`hand_server exited (code=${code}, signal=${signal})`);
      this.pythonProcess = undefined;
    });

    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  private stopHandServer(): void {
    if (!this.pythonProcess) {
      return;
    }
    this.pythonProcess.kill('SIGTERM');
    this.pythonProcess = undefined;
  }

  private getWebviewHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Marty Supreme Ping Pong</title>
  <style>
    :root {
      --bg: #0f1b2d;
      --bg2: #14294a;
      --fg: #f3f8ff;
      --accent: #f6c445;
      --muted: #8ea5c2;
      --paddle: #77d4ff;
      --ball: #ff7f5c;
    }
    body {
      margin: 0;
      font-family: Menlo, Monaco, Consolas, monospace;
      color: var(--fg);
      background: radial-gradient(circle at top right, #274b82 0%, var(--bg) 52%, #0a1320 100%);
      height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      border-bottom: 1px solid #2a3f61;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    #status {
      color: var(--accent);
    }
    #sub {
      color: var(--muted);
      font-size: 11px;
    }
    #gameWrap {
      position: relative;
      flex: 1;
      padding: 10px;
      min-height: 0;
    }
    canvas {
      width: 100%;
      height: 100%;
      display: block;
      border: 1px solid #2a3f61;
      border-radius: 8px;
      background: linear-gradient(180deg, #0d1a2b 0%, #0c1422 100%);
    }
    #overlay {
      position: absolute;
      inset: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      color: var(--muted);
      backdrop-filter: blur(2px);
      border-radius: 8px;
      border: 1px dashed #385782;
      pointer-events: none;
      font-size: 14px;
      line-height: 1.4;
      background: rgba(8, 16, 27, 0.55);
    }
    #overlay.hidden {
      display: none;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <div>Marty Supreme Think Pong</div>
      <div id="sub">Webcam runs in background process (no preview window). Raise your hand to steer.</div>
    </div>
    <div id="status">Idle</div>
  </header>
  <div id="gameWrap">
    <canvas id="game" width="900" height="560"></canvas>
    <div id="overlay">Waiting for thinking state...</div>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const statusEl = document.getElementById('status');
    const overlay = document.getElementById('overlay');
    const canvas = document.getElementById('game');
    const ctx = canvas.getContext('2d');

    let thinking = false;
    let ws = null;
    let lastHandX = 0.5;
    let lastHandY = 0.5;
    let handConfidence = 0;
    let keyboardY = 0.5;
    let keyUp = false;
    let keyDown = false;
    let scores = { left: 0, right: 0 };

    const state = {
      leftY: canvas.height / 2 - 54,
      rightY: canvas.height / 2 - 54,
      ballX: canvas.width / 2,
      ballY: canvas.height / 2,
      ballVX: 5,
      ballVY: 3.6,
      paddleW: 14,
      paddleH: 108,
      margin: 16
    };

    function setThinkingUI(active, reason = '') {
      thinking = active;
      statusEl.textContent = active ? 'Thinking' : 'Idle';
      overlay.classList.toggle('hidden', active);
      if (!active) {
        overlay.textContent = 'Idle. Start via command or @pingpong chat participant.';
      } else if (reason) {
        overlay.textContent = 'Thinking: ' + reason;
      }
    }

    function connectSocket(port) {
      if (ws) {
        ws.close();
      }
      ws = new WebSocket('ws://127.0.0.1:' + port);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (typeof msg.paddleX === 'number') {
            lastHandX = Math.max(0, Math.min(1, msg.paddleX));
          }
          if (typeof msg.paddleY === 'number') {
            lastHandY = Math.max(0, Math.min(1, msg.paddleY));
          } else if (typeof msg.paddleX === 'number') {
            lastHandY = Math.max(0, Math.min(1, msg.paddleX));
          }
          handConfidence = typeof msg.confidence === 'number' ? msg.confidence : 0;
        } catch (err) {
          console.error(err);
        }
      };
      ws.onclose = () => {
        if (thinking) {
          setTimeout(() => vscode.postMessage({ type: 'restart-server' }), 750);
        }
      };
    }

    function resetBall(direction = 1) {
      state.ballX = canvas.width / 2;
      state.ballY = canvas.height / 2;
      state.ballVX = 4.6 * direction;
      state.ballVY = (Math.random() * 4) - 2;
    }

    function update() {
      if (thinking) {
        const keyboardDelta = (keyDown ? 1 : 0) - (keyUp ? 1 : 0);
        keyboardY = Math.max(0, Math.min(1, keyboardY + keyboardDelta * 0.015));
        const sensorY = handConfidence >= 0.35 ? lastHandY : keyboardY;
        const targetY = (canvas.height - state.paddleH) * sensorY;
        state.leftY += (targetY - state.leftY) * 0.22;
      }

      const aiCenter = state.rightY + state.paddleH / 2;
      const chase = state.ballY - aiCenter;
      state.rightY += Math.max(-5, Math.min(5, chase * 0.11));
      state.rightY = Math.max(state.margin, Math.min(canvas.height - state.margin - state.paddleH, state.rightY));

      state.ballX += state.ballVX;
      state.ballY += state.ballVY;

      if (state.ballY < state.margin || state.ballY > canvas.height - state.margin) {
        state.ballVY *= -1;
      }

      const leftX = state.margin;
      const rightX = canvas.width - state.margin - state.paddleW;

      if (
        state.ballX < leftX + state.paddleW &&
        state.ballY > state.leftY &&
        state.ballY < state.leftY + state.paddleH &&
        state.ballVX < 0
      ) {
        state.ballVX = Math.abs(state.ballVX) + 0.25;
      }

      if (
        state.ballX > rightX &&
        state.ballY > state.rightY &&
        state.ballY < state.rightY + state.paddleH &&
        state.ballVX > 0
      ) {
        state.ballVX = -Math.abs(state.ballVX) - 0.25;
      }

      if (state.ballX < 0) {
        scores.right++;
        resetBall(1);
      } else if (state.ballX > canvas.width) {
        scores.left++;
        resetBall(-1);
      }

      state.leftY = Math.max(state.margin, Math.min(canvas.height - state.margin - state.paddleH, state.leftY));
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#3f6ba3';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 14]);
      ctx.beginPath();
      ctx.moveTo(canvas.width / 2, 0);
      ctx.lineTo(canvas.width / 2, canvas.height);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#77d4ff';
      ctx.fillRect(state.margin, state.leftY, state.paddleW, state.paddleH);
      ctx.fillStyle = '#99e6c5';
      ctx.fillRect(canvas.width - state.margin - state.paddleW, state.rightY, state.paddleW, state.paddleH);

      ctx.fillStyle = '#ff7f5c';
      ctx.beginPath();
      ctx.arc(state.ballX, state.ballY, 10, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#f3f8ff';
      ctx.font = '24px Menlo, monospace';
      ctx.fillText(String(scores.left), canvas.width / 2 - 52, 42);
      ctx.fillText(String(scores.right), canvas.width / 2 + 34, 42);

      ctx.font = '12px Menlo, monospace';
      ctx.fillStyle = '#8ea5c2';
      ctx.fillText('hand confidence: ' + handConfidence.toFixed(2), 14, 24);
      if (handConfidence < 0.35) {
        ctx.fillText('fallback: keyboard (W/S or Arrow Up/Down)', 14, 42);
      }
    }

    function loop() {
      update();
      draw();
      requestAnimationFrame(loop);
    }

    window.addEventListener('message', (event) => {
      const message = event.data || {};
      if (message.type === 'state') {
        setThinkingUI(Boolean(message.thinking), message.reason || '');
        if (message.thinking && message.port) {
          connectSocket(message.port);
        } else if (!message.thinking && ws) {
          ws.close();
        }
      }
    });

    window.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowUp' || event.key === 'w' || event.key === 'W') {
        keyUp = true;
      }
      if (event.key === 'ArrowDown' || event.key === 's' || event.key === 'S') {
        keyDown = true;
      }
    });

    window.addEventListener('keyup', (event) => {
      if (event.key === 'ArrowUp' || event.key === 'w' || event.key === 'W') {
        keyUp = false;
      }
      if (event.key === 'ArrowDown' || event.key === 's' || event.key === 'S') {
        keyDown = false;
      }
    });

    resetBall(Math.random() > 0.5 ? 1 : -1);
    loop();
  </script>
</body>
</html>`;
  }
}

export function activate(context: vscode.ExtensionContext) {
  console.log('Marty Supreme extension is now active!');

  // Create output channel for logging
  const outputChannel = vscode.window.createOutputChannel('Marty Supreme');
  outputChannel.appendLine('Marty Supreme extension activated!');
  const thinkingPong = new ThinkingPingPongController(context, outputChannel);

  // Register hello command
  const helloCommand = vscode.commands.registerCommand('marty-supreme.hello', () => {
    vscode.window.showInformationMessage('Hello from Marty Supreme! 🏓');
    outputChannel.appendLine('Hello command executed');
  });

  // Register example game command
  const exampleGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runExampleGame',
    async () => {
      outputChannel.show();
      outputChannel.appendLine('Starting example game...');

      try {
        // Create Python process manager
        const pythonManager = new PythonProcessManager(context, outputChannel);

        // Path to example game script
        const gameScriptPath = path.join(
          context.extensionPath,
          'python',
          'games',
          'example_game.py'
        );

        // Spawn the Python process
        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine('Example game started successfully!');
          vscode.window.showInformationMessage('Marty Supreme: Example game is running!');

          // Send initialization command
          pythonManager.sendMessage(process, {
            command: 'initialize',
            data: { message: 'Hello from VSCode!' },
          });

          // Set up message handler
          pythonManager.onMessage(process, (message) => {
            outputChannel.appendLine(`Game response: ${JSON.stringify(message)}`);

            if (message.type === 'state_update') {
              vscode.window.showInformationMessage(
                `Game State: ${JSON.stringify(message.state)}`
              );
            }
          });

          // Clean up on process exit
          process.on('exit', (code) => {
            outputChannel.appendLine(`Game process exited with code ${code}`);
            vscode.window.showInformationMessage('Game ended!');
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start game: ${errorMsg}`);
      }
    }
  );

  const startThinkingGameCommand = vscode.commands.registerCommand(
    'marty-supreme.startThinkingGame',
    async () => {
      outputChannel.show(true);
      try {
        await thinkingPong.startThinking('manual_command');
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        outputChannel.appendLine(`Failed to start thinking game: ${errorMsg}`);
        vscode.window.showErrorMessage(`Could not start thinking game: ${errorMsg}`);
      }
    }
  );

  const startThinkingGameDebugCommand = vscode.commands.registerCommand(
    'marty-supreme.startThinkingGameDebug',
    async () => {
      outputChannel.show(true);
      try {
        await thinkingPong.startThinking('manual_command_debug_preview', { debugPreview: true });
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        outputChannel.appendLine(`Failed to start thinking game (debug): ${errorMsg}`);
        vscode.window.showErrorMessage(
          `Could not start thinking game debug preview: ${errorMsg}`
        );
      }
    }
  );

  const stopThinkingGameCommand = vscode.commands.registerCommand(
    'marty-supreme.stopThinkingGame',
    () => {
      thinkingPong.stopThinking();
    }
  );

  // Chat Participant API availability depends on VS Code version.
  const chatApi = (vscode as any).chat;
  if (chatApi?.createChatParticipant) {
    const participant = chatApi.createChatParticipant(
      'pingpong.agent',
      async (request: any, _ctx: any, stream: any, token: vscode.CancellationToken) => {
        const prompt = typeof request?.prompt === 'string' ? request.prompt : '';
        await thinkingPong.startThinking('chat_request');
        stream.markdown('Running ping-pong while I think...');

        try {
          // Keep the game active while we "think". Replace with real model/tool logic.
          await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => resolve(), 1800);
            token.onCancellationRequested(() => {
              clearTimeout(timeout);
              reject(new Error('Chat request canceled'));
            });
          });

          const summary = prompt.trim().length > 0 ? prompt.trim() : 'No prompt text received.';
          stream.markdown(`Done. I was thinking while the game ran.\n\nPrompt summary: ${summary}`);
          return { metadata: { ranThinkingGame: true } };
        } finally {
          thinkingPong.stopThinking();
        }
      }
    );

    context.subscriptions.push(participant);
    outputChannel.appendLine('Chat participant registered: @pingpong');
  } else {
    outputChannel.appendLine(
      'Chat Participant API not available in this VS Code build. Use start/stop commands.'
    );
  }

  // Add commands to subscriptions
  context.subscriptions.push(helloCommand);
  context.subscriptions.push(exampleGameCommand);
  context.subscriptions.push(startThinkingGameCommand);
  context.subscriptions.push(startThinkingGameDebugCommand);
  context.subscriptions.push(stopThinkingGameCommand);
  context.subscriptions.push(thinkingPong);
  context.subscriptions.push(outputChannel);

  // Show welcome message
  vscode.window.showInformationMessage(
    'Marty Supreme is ready! Relive your Marty Supreme moment! 🏓'
  );
}

export function deactivate() {
  console.log('Marty Supreme extension is now deactivated');
}
