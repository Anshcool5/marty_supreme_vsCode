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

    const pythonBin = await resolvePythonInterpreter(this.context, this.output, {
      requiredModules: ['cv2', 'mediapipe', 'websockets'],
    });
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
      --bg: #2a160c;
      --bg2: #120a05;
      --fg: #f1dfbf;
      --accent: #d39a55;
      --muted: #c2a57e;
      --line: #8c6233;
      --panel: #3e2515;
      --paddle: #d5a66a;
      --paddleAi: #9f6b3b;
      --ball: #f2c27b;
    }
    body {
      margin: 0;
      font-family: Menlo, Monaco, Consolas, monospace;
      color: var(--fg);
      background: radial-gradient(circle at top right, #5a341a 0%, var(--bg) 50%, var(--bg2) 100%);
      height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
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
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(180deg, #2e1a10 0%, #1c110a 100%);
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
      border: 1px dashed var(--line);
      pointer-events: none;
      font-size: 14px;
      line-height: 1.4;
      background: rgba(16, 9, 5, 0.58);
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
    let wsReconnectTimer = null;
    let wsReconnectAttempts = 0;
    let wsPort = null;
    let wsRestartCooldownUntil = 0;
    let lastHandX = 0.5;
    let lastHandY = 0.5;
    let lastHandSampleTime = 0;
    let handVelocityY = 0;
    let handConfidence = 0;
    let handMode = 'idle';
    let handOk = false;
    let keyboardY = 0.5;
    let filteredSensorY = 0.5;
    let leftPaddleVel = 0;
    let lastFrameTime = performance.now();
    let gameStarted = false;
    let trackingStableFrames = 0;
    let keyUp = false;
    let keyDown = false;
    let scores = { left: 0, right: 0 };
    const control = {
      sensorFilterBase: 0.62,
      sensorFilterMotionBoost: 0.008,
      leadTimeMs: 285,
      springK: 92.0,
      damping: 4.6,
      velocityMatchGain: 18.2,
      directHandFeed: 1.25,
      maxVelPxPerSec: 8600,
      maxAccelPxPerSec2: 90000,
      deadZonePx: 0.3
    };
    let aiAimOffset = (Math.random() - 0.5) * 90;

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
      overlay.classList.toggle('hidden', active && gameStarted);
      if (!active) {
        overlay.textContent = 'Idle. Start via command or @pingpong chat participant.';
      } else if (!gameStarted) {
        overlay.textContent = 'Show LEFT palm to camera to start.';
      } else if (reason) {
        overlay.textContent = 'Thinking: ' + reason;
      }
    }

    function connectSocket(port, isReconnect = false) {
      wsPort = port;
      if (!isReconnect) {
        wsReconnectAttempts = 0;
      }
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
      if (ws) {
        ws.close();
      }
      ws = new WebSocket('ws://127.0.0.1:' + port);
      ws.onopen = () => {
        wsReconnectAttempts = 0;
        lastHandSampleTime = 0;
        handVelocityY = 0;
        leftPaddleVel = 0;
        handMode = 'idle';
        handOk = false;
      };
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (typeof msg.paddleX === 'number') {
            lastHandX = Math.max(0, Math.min(1, msg.paddleX));
          }
          const prevY = lastHandY;
          if (typeof msg.paddleY === 'number') {
            lastHandY = Math.max(0, Math.min(1, msg.paddleY));
          } else if (typeof msg.paddleX === 'number') {
            lastHandY = Math.max(0, Math.min(1, msg.paddleX));
          }
          const nowMs = performance.now();
          if (lastHandSampleTime > 0) {
            const dt = Math.max(1, nowMs - lastHandSampleTime);
            const instantVel = (lastHandY - prevY) / dt;
            handVelocityY = (handVelocityY * 0.68) + (instantVel * 0.32);
          }
          lastHandSampleTime = nowMs;
          handConfidence = typeof msg.confidence === 'number' ? msg.confidence : 0;
          handMode = typeof msg.mode === 'string' ? msg.mode : handMode;
          handOk = msg.ok !== false;
        } catch (err) {
          console.error(err);
        }
      };
      ws.onclose = () => {
        ws = null;
        if (!thinking) {
          return;
        }

        if (wsReconnectAttempts < 4 && wsPort !== null) {
          const retryDelay = 250 + (wsReconnectAttempts * 250);
          wsReconnectAttempts += 1;
          wsReconnectTimer = setTimeout(() => connectSocket(wsPort, true), retryDelay);
          return;
        }

        const now = Date.now();
        if (now >= wsRestartCooldownUntil) {
          wsRestartCooldownUntil = now + 5000;
          vscode.postMessage({ type: 'restart-server' });
        }
      };
    }

    function resetBall(direction = 1) {
      state.ballX = canvas.width / 2;
      state.ballY = canvas.height / 2;
      state.ballVX = 4.6 * direction;
      state.ballVY = (Math.random() * 4) - 2;
      aiAimOffset = (Math.random() - 0.5) * 90;
    }

    function update() {
      const now = performance.now();
      const dt = Math.min(0.05, Math.max(1 / 240, (now - lastFrameTime) / 1000));
      lastFrameTime = now;

      if (thinking) {
        const leftTrackingActive =
          handOk &&
          handMode === 'mediapipe_left_palm_y' &&
          handConfidence >= 0.55;
        if (!gameStarted) {
          trackingStableFrames = leftTrackingActive ? (trackingStableFrames + 1) : 0;
          if (trackingStableFrames >= 6) {
            gameStarted = true;
            overlay.classList.add('hidden');
            statusEl.textContent = 'Thinking';
          } else {
            overlay.classList.remove('hidden');
            statusEl.textContent = 'Waiting For Left Palm';
            overlay.textContent = 'Show LEFT palm steadily to start.';
          }
        }

        const keyboardDelta = (keyDown ? 1 : 0) - (keyUp ? 1 : 0);
        keyboardY = Math.max(0, Math.min(1, keyboardY + keyboardDelta * 0.015));
        const rawSensorY = handConfidence >= 0.35 ? lastHandY : keyboardY;
        const sensorMotion = Math.abs(handVelocityY) * 1000;
        const alpha = Math.min(
          0.82,
          control.sensorFilterBase + (sensorMotion * control.sensorFilterMotionBoost)
        );
        filteredSensorY += (rawSensorY - filteredSensorY) * alpha;

        // Lead the target slightly using measured hand velocity so paddle speed matches quick hand motion.
        const predictedSensorY = Math.max(
          0,
          Math.min(1, filteredSensorY + (handVelocityY * control.leadTimeMs))
        );
        const targetY = (canvas.height - state.paddleH) * predictedSensorY;
        const targetVel = handVelocityY * (canvas.height - state.paddleH) * 1000;
        const posErr = targetY - state.leftY;
        const speedBoost = Math.min(1.0, Math.abs(handVelocityY) * 2000);
        const springK = control.springK + (16.0 * speedBoost);
        const velocityMatchGain = control.velocityMatchGain + (2.0 * speedBoost);

        let accel =
          (posErr * springK) +
          ((targetVel - leftPaddleVel) * velocityMatchGain) -
          (leftPaddleVel * control.damping);

        accel = Math.max(-control.maxAccelPxPerSec2, Math.min(control.maxAccelPxPerSec2, accel));
        leftPaddleVel += accel * dt;
        leftPaddleVel += targetVel * control.directHandFeed * dt;
        leftPaddleVel = Math.max(
          -control.maxVelPxPerSec,
          Math.min(control.maxVelPxPerSec, leftPaddleVel)
        );

        if (Math.abs(posErr) < control.deadZonePx && Math.abs(leftPaddleVel) < 12) {
          leftPaddleVel = 0;
        }

        state.leftY += leftPaddleVel * dt;
      } else {
        leftPaddleVel *= 0.86;
      }

      if (gameStarted) {
        const aiTarget = state.ballVX > 0
          ? (state.ballY - (state.paddleH / 2) + aiAimOffset + (Math.sin(performance.now() / 240) * 5))
          : ((canvas.height - state.paddleH) / 2) + (aiAimOffset * 0.18);
        const aiFollow = state.ballVX > 0 ? 0.1 : 0.06;
        const aiMaxStep = state.ballVX > 0 ? 3.9 : 2.8;
        const aiStep = (aiTarget - state.rightY) * aiFollow;
        state.rightY += Math.max(-aiMaxStep, Math.min(aiMaxStep, aiStep));
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

        const aiHitTop = state.rightY + 8;
        const aiHitBottom = state.rightY + state.paddleH - 8;
        if (
          state.ballX > rightX &&
          state.ballY > aiHitTop &&
          state.ballY < aiHitBottom &&
          state.ballVX > 0 &&
          Math.random() > 0.03
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
      }

      const minY = state.margin;
      const maxY = canvas.height - state.margin - state.paddleH;
      if (state.leftY < minY) {
        state.leftY = minY;
        leftPaddleVel = 0;
      } else if (state.leftY > maxY) {
        state.leftY = maxY;
        leftPaddleVel = 0;
      }

      state.leftY = Math.max(state.margin, Math.min(canvas.height - state.margin - state.paddleH, state.leftY));
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#8c6233';
      ctx.lineWidth = 2;
      ctx.setLineDash([8, 14]);
      ctx.beginPath();
      ctx.moveTo(canvas.width / 2, 0);
      ctx.lineTo(canvas.width / 2, canvas.height);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#d5a66a';
      ctx.fillRect(state.margin, state.leftY, state.paddleW, state.paddleH);
      ctx.fillStyle = '#9f6b3b';
      ctx.fillRect(canvas.width - state.margin - state.paddleW, state.rightY, state.paddleW, state.paddleH);

      ctx.fillStyle = '#f2c27b';
      ctx.beginPath();
      ctx.arc(state.ballX, state.ballY, 10, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#f1dfbf';
      ctx.font = '24px Menlo, monospace';
      ctx.fillText(String(scores.left), canvas.width / 2 - 52, 42);
      ctx.fillText(String(scores.right), canvas.width / 2 + 34, 42);

      ctx.font = '12px Menlo, monospace';
      ctx.fillStyle = '#c2a57e';
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
        if (message.thinking) {
          gameStarted = false;
          trackingStableFrames = 0;
          handMode = 'idle';
          handOk = false;
          handConfidence = 0;
          resetBall(Math.random() > 0.5 ? 1 : -1);
        }
        setThinkingUI(Boolean(message.thinking), message.reason || '');
        if (message.thinking && message.port) {
          wsRestartCooldownUntil = 0;
          connectSocket(message.port);
        } else if (!message.thinking && ws) {
          if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
          }
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

  // Register Tetris game command
  const tetrisGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runTetris',
    async () => {
      outputChannel.show();
      outputChannel.appendLine('Starting Tetris 1926...');

      try {
        const pythonManager = new PythonProcessManager(context, outputChannel);

        const gameScriptPath = path.join(
          context.extensionPath,
          'python',
          'games',
          'tetris.py'
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine('Tetris 1926 started successfully!');
          vscode.window.showInformationMessage('Marty Supreme: Tetris 1926 is running!');

          process.on('exit', (code) => {
            outputChannel.appendLine(`Tetris process exited with code ${code}`);
            vscode.window.showInformationMessage('Tetris 1926 ended.');
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Tetris: ${errorMsg}`);
      }
    }
  );

  // Register Blackjack game command
  const blackjackGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runBlackjack',
    async () => {
      outputChannel.show();
      outputChannel.appendLine('Starting Blackjack 1940s...');

      try {
        const pythonManager = new PythonProcessManager(context, outputChannel);

        const gameScriptPath = path.join(
          context.extensionPath,
          'python',
          'games',
          'blackjack.py'
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine('Blackjack 1940s started successfully!');
          vscode.window.showInformationMessage('Marty Supreme: Blackjack 1940s is running!');

          process.on('exit', (code) => {
            outputChannel.appendLine(`Blackjack process exited with code ${code}`);
            vscode.window.showInformationMessage('Blackjack 1940s ended.');
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Blackjack: ${errorMsg}`);
      }
    }
  );

  // Register Pong game command (hand-tracked)
  const pongGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runPong',
    async () => {
      outputChannel.show();
      outputChannel.appendLine('Starting Pong 1950 (hand tracking)...');

      try {
        const pythonManager = new PythonProcessManager(context, outputChannel);
        const gameScriptPath = path.join(
          context.extensionPath,
          'python',
          'games',
          'hand_server.py'
        );

        const process = await pythonManager.spawn(gameScriptPath, [
          '--run-pong',
          '--show-preview',
        ]);

        if (process) {
          outputChannel.appendLine('Pong 1950 started successfully!');
          vscode.window.showInformationMessage(
            'Marty Supreme: Pong 1950 is running!'
          );

          process.on('exit', (code) => {
            outputChannel.appendLine(`Pong process exited with code ${code}`);
            vscode.window.showInformationMessage('Pong 1950 ended.');
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Pong: ${errorMsg}`);
      }
    }
  );

  // Add commands to subscriptions
  context.subscriptions.push(helloCommand);
  context.subscriptions.push(exampleGameCommand);
  context.subscriptions.push(tetrisGameCommand);
  context.subscriptions.push(blackjackGameCommand);
  context.subscriptions.push(pongGameCommand);
  context.subscriptions.push(outputChannel);

  // Show welcome message
  vscode.window.showInformationMessage(
    'Marty Supreme is ready! Relive your Marty Supreme moment! 🏓'
  );
}

export function deactivate() {
  console.log('Marty Supreme extension is now deactivated');
}
