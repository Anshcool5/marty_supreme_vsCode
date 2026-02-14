import * as vscode from 'vscode';
import { PythonProcessManager } from './python/processManager';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import * as readline from 'readline';

interface MonitorConfig {
  x: number;
  y: number;
  width: number;
  height: number;
  thinkingIconPath: string;
  readyIconPath: string;
  threshold: number;
  intervalMs: number;
  stableFrames: number;
}

const MONITOR_CONFIG_KEY = 'martySupreme.monitorConfig';

class MartyController implements vscode.Disposable {
  private pongProcess: ChildProcess | undefined;
  private monitorProcess: ChildProcess | undefined;
  private lastMonitorState: 'thinking' | 'ready' | 'unknown' = 'unknown';

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly output: vscode.OutputChannel
  ) {}

  dispose(): void {
    this.stopAutoMonitor();
    this.stopPong();
  }

  private getDefaultMonitorConfig(): MonitorConfig {
    return {
      x: 70,
      y: 69,
      width: 98,
      height: 98,
      thinkingIconPath: '',
      readyIconPath: '',
      threshold: 0.74,
      intervalMs: 120,
      stableFrames: 3,
    };
  }

  private getMonitorConfig(): MonitorConfig {
    const stored = this.context.globalState.get<MonitorConfig>(MONITOR_CONFIG_KEY);
    return { ...this.getDefaultMonitorConfig(), ...(stored ?? {}) };
  }

  private async saveMonitorConfig(config: MonitorConfig): Promise<void> {
    await this.context.globalState.update(MONITOR_CONFIG_KEY, config);
  }

  private async askNumber(
    prompt: string,
    initial: number,
    validate: (n: number) => boolean
  ): Promise<number | undefined> {
    const value = await vscode.window.showInputBox({
      prompt,
      value: String(initial),
      ignoreFocusOut: true,
      validateInput: (raw) => {
        const n = Number(raw);
        if (!Number.isFinite(n) || !validate(n)) {
          return 'Enter a valid number.';
        }
        return null;
      },
    });

    if (value === undefined) {
      return undefined;
    }

    return Number(value);
  }

  async configureMonitorRegion(): Promise<void> {
    const config = this.getMonitorConfig();

    const x = await this.askNumber('Monitor region X (screen px)', config.x, (n) => n >= 0);
    if (x === undefined) {
      return;
    }

    const y = await this.askNumber('Monitor region Y (screen px)', config.y, (n) => n >= 0);
    if (y === undefined) {
      return;
    }

    const width = await this.askNumber('Monitor region WIDTH (screen px)', config.width, (n) => n > 20);
    if (width === undefined) {
      return;
    }

    const height = await this.askNumber('Monitor region HEIGHT (screen px)', config.height, (n) => n > 20);
    if (height === undefined) {
      return;
    }

    const next: MonitorConfig = { ...config, x, y, width, height };
    await this.saveMonitorConfig(next);
    this.output.appendLine(`Saved monitor region: x=${x} y=${y} w=${width} h=${height}`);
    vscode.window.showInformationMessage('Marty Supreme: Monitor region saved.');
  }

  async configureMonitorRegionInteractive(): Promise<void> {
    const python = await this.resolvePython(['cv2', 'numpy', 'mss']);
    const script = path.join(this.context.extensionPath, 'python', 'games', 'ui_icon_monitor.py');

    if (!fs.existsSync(script)) {
      vscode.window.showErrorMessage('Marty Supreme: ui_icon_monitor.py is missing.');
      return;
    }

    this.output.appendLine(
      `Starting interactive ROI picker: ${python} ${script} --interactive-select`
    );
    vscode.window.showInformationMessage(
      'Marty Supreme: Draw a box on screen and press ENTER (or ESC to cancel).'
    );

    const proc = spawn(python, ['-u', script, '--interactive-select'], {
      cwd: this.context.extensionPath,
      env: { ...process.env },
    });

    let selectedRegion: { x: number; y: number; width: number; height: number } | null = null;

    const rl = readline.createInterface({
      input: proc.stdout!,
      crlfDelay: Infinity,
    });

    rl.on('line', (line) => {
      try {
        const payload = JSON.parse(line) as {
          type?: string;
          x?: number;
          y?: number;
          width?: number;
          height?: number;
        };

        if (
          payload.type === 'roi_selected' &&
          typeof payload.x === 'number' &&
          typeof payload.y === 'number' &&
          typeof payload.width === 'number' &&
          typeof payload.height === 'number'
        ) {
          selectedRegion = {
            x: payload.x,
            y: payload.y,
            width: payload.width,
            height: payload.height,
          };
        } else if (payload.type === 'roi_cancelled') {
          this.output.appendLine('Interactive ROI selection cancelled.');
        } else {
          this.output.appendLine(`[monitor-roi] ${line}`);
        }
      } catch {
        this.output.appendLine(`[monitor-roi] ${line}`);
      }
    });

    proc.stderr?.on('data', (data: Buffer) => {
      this.output.appendLine(`[monitor-roi:stderr] ${data.toString().trimEnd()}`);
    });

    await new Promise<void>((resolve) => {
      proc.on('exit', async (code, signal) => {
        this.output.appendLine(`Interactive ROI picker exited (code=${code}, signal=${signal})`);
        if (code === 0 && selectedRegion) {
          const config = this.getMonitorConfig();
          const next: MonitorConfig = { ...config, ...selectedRegion };
          await this.saveMonitorConfig(next);
          vscode.window.showInformationMessage(
            `Marty Supreme: ROI saved x=${next.x}, y=${next.y}, w=${next.width}, h=${next.height}`
          );
        } else if (code === 2) {
          vscode.window.showInformationMessage('Marty Supreme: ROI selection cancelled.');
        } else if (code !== 0) {
          vscode.window.showErrorMessage('Marty Supreme: ROI picker failed. Check Output logs.');
        }
        resolve();
      });
    });
  }

  async configureMonitorIcons(): Promise<void> {
    const config = this.getMonitorConfig();

    const thinkingIconPath = await vscode.window.showInputBox({
      prompt: 'Path to STOP icon template image (thinking state)',
      value: config.thinkingIconPath,
      ignoreFocusOut: true,
    });
    if (thinkingIconPath === undefined) {
      return;
    }

    const readyIconPath = await vscode.window.showInputBox({
      prompt: 'Path to ARROW icon template image (ready state)',
      value: config.readyIconPath,
      ignoreFocusOut: true,
    });
    if (readyIconPath === undefined) {
      return;
    }

    const next: MonitorConfig = {
      ...config,
      thinkingIconPath: thinkingIconPath.trim(),
      readyIconPath: readyIconPath.trim(),
    };

    await this.saveMonitorConfig(next);
    this.output.appendLine('Saved monitor icon template paths.');
    vscode.window.showInformationMessage('Marty Supreme: Monitor icon templates saved.');
  }

  async configureMonitorAdvanced(): Promise<void> {
    const config = this.getMonitorConfig();

    const threshold = await this.askNumber(
      'Template threshold (0.0-1.0, recommended 0.74)',
      config.threshold,
      (n) => n > 0.2 && n <= 1.0
    );
    if (threshold === undefined) {
      return;
    }

    const intervalMs = await this.askNumber(
      'Polling interval in ms (recommended 120)',
      config.intervalMs,
      (n) => n >= 40 && n <= 2000
    );
    if (intervalMs === undefined) {
      return;
    }

    const stableFrames = await this.askNumber(
      'Stable frames before state switch (recommended 3)',
      config.stableFrames,
      (n) => n >= 1 && n <= 30
    );
    if (stableFrames === undefined) {
      return;
    }

    const next: MonitorConfig = { ...config, threshold, intervalMs, stableFrames };
    await this.saveMonitorConfig(next);
    this.output.appendLine(
      `Saved monitor advanced settings: threshold=${threshold}, interval=${intervalMs}, stable=${stableFrames}`
    );
    vscode.window.showInformationMessage('Marty Supreme: Monitor advanced settings saved.');
  }

  private async resolvePython(requiredModules: string[] = []): Promise<string> {
    const configuredInterpreter = vscode.workspace
      .getConfiguration('python')
      .get<string>('defaultInterpreterPath');

    const candidates: string[] = [];
    const add = (entry: string | undefined) => {
      if (!entry) {
        return;
      }
      if (!candidates.includes(entry)) {
        candidates.push(entry);
      }
    };

    const toWorkspacePath = (raw: string): string => {
      const trimmed = raw.trim();
      if (trimmed.length === 0) {
        return trimmed;
      }
      if (path.isAbsolute(trimmed)) {
        return trimmed;
      }
      return path.join(this.context.extensionPath, trimmed);
    };

    if (configuredInterpreter) {
      add(toWorkspacePath(configuredInterpreter.replace('${workspaceFolder}', this.context.extensionPath)));
    }

    const localVenvs = [
      path.join(this.context.extensionPath, 'python', 'venv', 'bin', 'python'),
      path.join(this.context.extensionPath, 'python', 'venv', 'bin', 'python3'),
      path.join(this.context.extensionPath, 'python', 'venv', 'Scripts', 'python.exe'),
      path.join(this.context.extensionPath, 'python', '.venv', 'bin', 'python'),
      path.join(this.context.extensionPath, 'python', '.venv', 'bin', 'python3'),
      path.join(this.context.extensionPath, 'python', '.venv', 'Scripts', 'python.exe'),
    ];

    for (const candidate of localVenvs) {
      if (fs.existsSync(candidate)) {
        add(candidate);
      }
    }

    add(process.env.MARTY_SUPREME_PYTHON);
    add('python3');
    add('python');
    add('py');

    for (const candidate of candidates) {
      const available = await new Promise<boolean>((resolve) => {
        const probe = spawn(candidate, ['--version']);
        probe.on('error', () => resolve(false));
        probe.on('exit', (code) => resolve(code === 0));
      });

      if (!available) {
        continue;
      }

      if (requiredModules.length > 0) {
        const modulesOk = await new Promise<boolean>((resolve) => {
          const script =
            'import importlib.util,sys\n' +
            `mods=${JSON.stringify(requiredModules)}\n` +
            'missing=[m for m in mods if importlib.util.find_spec(m) is None]\n' +
            'sys.exit(0 if not missing else 2)\n';

          const probe = spawn(candidate, ['-c', script]);
          probe.on('error', () => resolve(false));
          probe.on('exit', (code) => resolve(code === 0));
        });

        if (!modulesOk) {
          this.output.appendLine(
            `Skipping Python interpreter (missing modules ${requiredModules.join(', ')}): ${candidate}`
          );
          continue;
        }
      }

      this.output.appendLine(`Using Python interpreter: ${candidate}`);
      return candidate;
    }

    throw new Error(
      `No usable Python interpreter found for modules: ${requiredModules.join(', ') || 'none'}`
    );
  }

  async startPong(showPreview = true): Promise<void> {
    if (this.pongProcess) {
      this.output.appendLine('Pong already running.');
      return;
    }

    const python = await this.resolvePython(['cv2', 'mediapipe', 'pygame']);
    const script = path.join(this.context.extensionPath, 'python', 'games', 'hand_server.py');
    const args = ['-u', script, '--run-pong'];
    if (showPreview) {
      args.push('--show-preview');
    }

    this.output.appendLine(`Starting Pong process: ${python} ${args.slice(1).join(' ')}`);
    this.pongProcess = spawn(python, args, {
      cwd: this.context.extensionPath,
      env: { ...process.env },
    });

    this.pongProcess.stdout?.on('data', (data: Buffer) => {
      this.output.appendLine(`[pong] ${data.toString().trimEnd()}`);
    });

    this.pongProcess.stderr?.on('data', (data: Buffer) => {
      this.output.appendLine(`[pong:stderr] ${data.toString().trimEnd()}`);
    });

    this.pongProcess.on('exit', (code, signal) => {
      this.output.appendLine(`Pong exited (code=${code}, signal=${signal})`);
      this.pongProcess = undefined;
    });
  }

  stopPong(): void {
    if (!this.pongProcess) {
      return;
    }
    this.output.appendLine('Stopping Pong process...');
    this.pongProcess.kill('SIGTERM');
    this.pongProcess = undefined;
  }

  private async handleMonitorState(state: 'thinking' | 'ready' | 'unknown', readyScore: number, thinkingScore: number): Promise<void> {
    if (state === this.lastMonitorState) {
      return;
    }

    this.lastMonitorState = state;
    this.output.appendLine(
      `Monitor state => ${state} (ready=${readyScore.toFixed(3)}, thinking=${thinkingScore.toFixed(3)})`
    );

    if (state === 'thinking') {
      await this.startPong(false);
      return;
    }

    if (state === 'ready') {
      this.stopPong();
    }
  }

  private validateMonitorConfig(config: MonitorConfig): string | null {
    if (config.width <= 0 || config.height <= 0) {
      return 'Invalid region size. Configure monitor region first.';
    }
    if (!config.thinkingIconPath || !config.readyIconPath) {
      return 'Missing icon templates. Configure monitor icon paths first.';
    }
    if (!fs.existsSync(config.thinkingIconPath)) {
      return `Thinking icon file not found: ${config.thinkingIconPath}`;
    }
    if (!fs.existsSync(config.readyIconPath)) {
      return `Ready icon file not found: ${config.readyIconPath}`;
    }
    return null;
  }

  async startAutoMonitor(): Promise<void> {
    if (this.monitorProcess) {
      vscode.window.showInformationMessage('Marty Supreme: Agent icon monitor is already running.');
      return;
    }

    const config = this.getMonitorConfig();
    const validationError = this.validateMonitorConfig(config);
    if (validationError) {
      vscode.window.showErrorMessage(`Marty Supreme: ${validationError}`);
      return;
    }

    const python = await this.resolvePython(['cv2', 'numpy', 'mss']);
    const script = path.join(this.context.extensionPath, 'python', 'games', 'ui_icon_monitor.py');

    if (!fs.existsSync(script)) {
      vscode.window.showErrorMessage('Marty Supreme: ui_icon_monitor.py is missing.');
      return;
    }

    const args = [
      '-u',
      script,
      '--x',
      String(config.x),
      '--y',
      String(config.y),
      '--width',
      String(config.width),
      '--height',
      String(config.height),
      '--thinking-icon',
      config.thinkingIconPath,
      '--ready-icon',
      config.readyIconPath,
      '--threshold',
      String(config.threshold),
      '--interval-ms',
      String(config.intervalMs),
      '--stable-frames',
      String(config.stableFrames),
    ];

    this.output.appendLine(`Starting UI monitor: ${python} ${args.slice(1).join(' ')}`);
    this.monitorProcess = spawn(python, args, {
      cwd: this.context.extensionPath,
      env: { ...process.env },
    });

    const rl = readline.createInterface({
      input: this.monitorProcess.stdout!,
      crlfDelay: Infinity,
    });

    rl.on('line', async (line) => {
      try {
        const payload = JSON.parse(line) as {
          type?: string;
          state?: 'thinking' | 'ready' | 'unknown';
          readyScore?: number;
          thinkingScore?: number;
        };

        if (payload.type === 'state' && payload.state) {
          await this.handleMonitorState(
            payload.state,
            payload.readyScore ?? 0,
            payload.thinkingScore ?? 0
          );
        } else if (payload.type === 'heartbeat') {
          const ready = payload.readyScore ?? 0;
          const thinking = payload.thinkingScore ?? 0;
          this.output.appendLine(
            `Monitor heartbeat (state=${payload.state ?? 'unknown'}, ready=${ready.toFixed(3)}, thinking=${thinking.toFixed(3)})`
          );
        } else {
          this.output.appendLine(`[monitor] ${line}`);
        }
      } catch {
        this.output.appendLine(`[monitor] ${line}`);
      }
    });

    this.monitorProcess.stderr?.on('data', (data: Buffer) => {
      this.output.appendLine(`[monitor:stderr] ${data.toString().trimEnd()}`);
    });

    this.monitorProcess.on('exit', (code, signal) => {
      this.output.appendLine(`UI monitor exited (code=${code}, signal=${signal})`);
      this.monitorProcess = undefined;
      this.lastMonitorState = 'unknown';
    });

    vscode.window.showInformationMessage('Marty Supreme: Agent icon monitor started.');
  }

  async captureMonitorSnippet(seconds = 5): Promise<void> {
    const config = this.getMonitorConfig();
    const validationError = this.validateMonitorConfig(config);
    if (validationError) {
      vscode.window.showErrorMessage(`Marty Supreme: ${validationError}`);
      return;
    }

    const python = await this.resolvePython(['cv2', 'numpy', 'mss']);
    const script = path.join(this.context.extensionPath, 'python', 'games', 'ui_icon_monitor.py');

    if (!fs.existsSync(script)) {
      vscode.window.showErrorMessage('Marty Supreme: ui_icon_monitor.py is missing.');
      return;
    }

    const outDir = path.join(this.context.extensionPath, 'python', 'monitor_previews');
    fs.mkdirSync(outDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const previewPath = path.join(outDir, `monitor_preview_${stamp}.mp4`);

    const args = [
      '-u',
      script,
      '--x',
      String(config.x),
      '--y',
      String(config.y),
      '--width',
      String(config.width),
      '--height',
      String(config.height),
      '--thinking-icon',
      config.thinkingIconPath,
      '--ready-icon',
      config.readyIconPath,
      '--threshold',
      String(config.threshold),
      '--interval-ms',
      String(config.intervalMs),
      '--stable-frames',
      String(config.stableFrames),
      '--preview-seconds',
      String(seconds),
      '--preview-output',
      previewPath,
    ];

    this.output.appendLine(`Capturing monitor preview: ${python} ${args.slice(1).join(' ')}`);
    vscode.window.showInformationMessage(`Marty Supreme: Capturing ${seconds}s monitor preview...`);

    const proc = spawn(python, args, {
      cwd: this.context.extensionPath,
      env: { ...process.env },
    });

    const rl = readline.createInterface({
      input: proc.stdout!,
      crlfDelay: Infinity,
    });

    rl.on('line', (line) => {
      try {
        const payload = JSON.parse(line) as { type?: string; previewOutput?: string };
        if (payload.type === 'preview_saved') {
          const savedPath = payload.previewOutput ?? previewPath;
          this.output.appendLine(`Monitor preview saved: ${savedPath}`);
        } else {
          this.output.appendLine(`[monitor-preview] ${line}`);
        }
      } catch {
        this.output.appendLine(`[monitor-preview] ${line}`);
      }
    });

    proc.stderr?.on('data', (data: Buffer) => {
      this.output.appendLine(`[monitor-preview:stderr] ${data.toString().trimEnd()}`);
    });

    proc.on('exit', (code, signal) => {
      this.output.appendLine(`Monitor preview exited (code=${code}, signal=${signal})`);
      if (code === 0) {
        vscode.window.showInformationMessage(`Marty Supreme: Preview saved at ${previewPath}`);
      } else {
        vscode.window.showErrorMessage('Marty Supreme: Monitor preview capture failed. Check Output logs.');
      }
    });
  }

  stopAutoMonitor(): void {
    if (!this.monitorProcess) {
      return;
    }
    this.output.appendLine('Stopping UI monitor...');
    this.monitorProcess.kill('SIGTERM');
    this.monitorProcess = undefined;
    this.lastMonitorState = 'unknown';
  }
}

let controller: MartyController | undefined;

export function activate(context: vscode.ExtensionContext) {
  console.log('Marty Supreme extension is now active!');

  const outputChannel = vscode.window.createOutputChannel('Marty Supreme');
  outputChannel.appendLine('Marty Supreme extension activated!');

  controller = new MartyController(context, outputChannel);

  const helloCommand = vscode.commands.registerCommand('marty-supreme.hello', () => {
    vscode.window.showInformationMessage('Hello from Marty Supreme! 🏓');
    outputChannel.appendLine('Hello command executed');
  });

  const exampleGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runExampleGame',
    async () => {
      outputChannel.show();
      outputChannel.appendLine('Starting example game...');

      try {
        const pythonManager = new PythonProcessManager(context, outputChannel);
        const gameScriptPath = path.join(
          context.extensionPath,
          'python',
          'games',
          'example_game.py'
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine('Example game started successfully!');
          vscode.window.showInformationMessage('Marty Supreme: Example game is running!');

          pythonManager.sendMessage(process, {
            command: 'initialize',
            data: { message: 'Hello from VSCode!' },
          });

          pythonManager.onMessage(process, (message) => {
            outputChannel.appendLine(`Game response: ${JSON.stringify(message)}`);

            if (message.type === 'state_update') {
              vscode.window.showInformationMessage(
                `Game State: ${JSON.stringify(message.state)}`
              );
            }
          });

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

  const pongGameCommand = vscode.commands.registerCommand(
    'marty-supreme.runPong',
    async () => {
      outputChannel.show();
      try {
        await controller?.startPong(true);
        vscode.window.showInformationMessage('Marty Supreme: Pong 1950 is running!');
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Pong: ${errorMsg}`);
      }
    }
  );

  const stopPongCommand = vscode.commands.registerCommand('marty-supreme.stopPong', () => {
    controller?.stopPong();
    vscode.window.showInformationMessage('Marty Supreme: Pong stopped.');
  });

  const configureMonitorRegionCommand = vscode.commands.registerCommand(
    'marty-supreme.configureMonitorRegion',
    async () => {
      outputChannel.show(true);
      await controller?.configureMonitorRegion();
    }
  );

  const configureMonitorRegionInteractiveCommand = vscode.commands.registerCommand(
    'marty-supreme.configureMonitorRegionInteractive',
    async () => {
      outputChannel.show(true);
      await controller?.configureMonitorRegionInteractive();
    }
  );

  const configureMonitorIconsCommand = vscode.commands.registerCommand(
    'marty-supreme.configureMonitorIcons',
    async () => {
      outputChannel.show(true);
      await controller?.configureMonitorIcons();
    }
  );

  const configureMonitorAdvancedCommand = vscode.commands.registerCommand(
    'marty-supreme.configureMonitorAdvanced',
    async () => {
      outputChannel.show(true);
      await controller?.configureMonitorAdvanced();
    }
  );

  const startAutoMonitorCommand = vscode.commands.registerCommand(
    'marty-supreme.startAutoMonitor',
    async () => {
      outputChannel.show(true);
      try {
        await controller?.startAutoMonitor();
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start monitor: ${errorMsg}`);
      }
    }
  );

  const stopAutoMonitorCommand = vscode.commands.registerCommand(
    'marty-supreme.stopAutoMonitor',
    () => {
      controller?.stopAutoMonitor();
      controller?.stopPong();
      vscode.window.showInformationMessage('Marty Supreme: Agent monitor stopped.');
    }
  );

  const captureMonitorSnippetCommand = vscode.commands.registerCommand(
    'marty-supreme.captureMonitorSnippet',
    async () => {
      outputChannel.show(true);
      try {
        await controller?.captureMonitorSnippet(5);
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred';
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to capture monitor snippet: ${errorMsg}`);
      }
    }
  );

  context.subscriptions.push(helloCommand);
  context.subscriptions.push(exampleGameCommand);
  context.subscriptions.push(tetrisGameCommand);
  context.subscriptions.push(blackjackGameCommand);
  context.subscriptions.push(pongGameCommand);
  context.subscriptions.push(stopPongCommand);
  context.subscriptions.push(configureMonitorRegionCommand);
  context.subscriptions.push(configureMonitorRegionInteractiveCommand);
  context.subscriptions.push(configureMonitorIconsCommand);
  context.subscriptions.push(configureMonitorAdvancedCommand);
  context.subscriptions.push(startAutoMonitorCommand);
  context.subscriptions.push(stopAutoMonitorCommand);
  context.subscriptions.push(captureMonitorSnippetCommand);
  context.subscriptions.push(controller);
  context.subscriptions.push(outputChannel);

  vscode.window.showInformationMessage(
    'Marty Supreme is ready! Relive your Marty Supreme moment! 🏓'
  );
}

export function deactivate() {
  controller?.dispose();
  controller = undefined;
  console.log('Marty Supreme extension is now deactivated');
}
