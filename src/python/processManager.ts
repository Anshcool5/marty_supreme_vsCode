import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';
import * as readline from 'readline';
import * as fs from 'fs';
import * as path from 'path';
import { resolvePythonInterpreter } from './interpreter';

export class PythonProcessManager {
  private processes: Map<string, ChildProcess> = new Map();
  private messageHandlers: Map<string, (message: any) => void> = new Map();

  constructor(
    private context: vscode.ExtensionContext,
    private outputChannel: vscode.OutputChannel
  ) {}

  /**
   * Find Python executable in system
   */
  private async findPythonExecutable(): Promise<string> {
    // Prefer the workspace venv interpreter so installed game deps (e.g. OpenCV) are available.
    const venvCandidates = [
      path.join(this.context.extensionPath, 'python', 'venv', 'bin', 'python'),
      path.join(this.context.extensionPath, 'python', 'venv', 'Scripts', 'python.exe'),
    ];
    const pythonCommands: string[] = [];

    for (const candidate of venvCandidates) {
      if (fs.existsSync(candidate)) {
        pythonCommands.push(candidate);
      }
    }

    // Try common Python commands
    pythonCommands.push('python3', 'python', 'py');

    for (const cmd of pythonCommands) {
      try {
        // Test if command exists
        const testProcess = spawn(cmd, ['--version']);
        const result = await new Promise<boolean>((resolve) => {
          testProcess.on('error', () => resolve(false));
          testProcess.on('exit', (code) => resolve(code === 0));
        });

        if (result) {
          this.outputChannel.appendLine(`Found Python: ${cmd}`);
          return cmd;
        }
      } catch (error) {
        continue;
      }
    }

    throw new Error(
      'Python not found. Please install Python 3.8+ and ensure it is in your PATH.'
    );
    return resolvePythonInterpreter(this.context, this.outputChannel);
  }

  /**
   * Spawn a Python process with the given script path
   */
  async spawn(scriptPath: string, args: string[] = []): Promise<ChildProcess | null> {
    try {
      const pythonCmd = await this.findPythonExecutable();
      this.outputChannel.appendLine(`Spawning Python process: ${pythonCmd} ${scriptPath}`);

      const childProcess = spawn(pythonCmd, ['-u', scriptPath, ...args], {
        cwd: this.context.extensionPath,
        env: { ...globalThis.process.env },
      });

      const processId = `${Date.now()}-${Math.random()}`;
      this.processes.set(processId, childProcess);

      // Set up line-by-line reading from stdout
      const rl = readline.createInterface({
        input: childProcess.stdout!,
        crlfDelay: Infinity,
      });

      rl.on('line', (line) => {
        try {
          const message = JSON.parse(line);
          this.outputChannel.appendLine(`Received: ${line}`);

          const handler = this.messageHandlers.get(processId);
          if (handler) {
            handler(message);
          }
        } catch (error) {
          // Not JSON, treat as regular output
          this.outputChannel.appendLine(`Python stdout: ${line}`);
        }
      });

      // Capture stderr
      childProcess.stderr!.on('data', (data: Buffer) => {
        this.outputChannel.appendLine(`Python stderr: ${data.toString()}`);
      });

      // Handle process errors
      childProcess.on('error', (error: Error) => {
        this.outputChannel.appendLine(`Process error: ${error.message}`);
        vscode.window.showErrorMessage(`Python process error: ${error.message}`);
      });

      // Cleanup on exit
      childProcess.on('exit', (code: number | null, signal: string | null) => {
        this.outputChannel.appendLine(
          `Process exited with code ${code}, signal ${signal}`
        );
        this.processes.delete(processId);
        this.messageHandlers.delete(processId);
      });

      return childProcess;
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      this.outputChannel.appendLine(`Failed to spawn Python process: ${errorMsg}`);
      vscode.window.showErrorMessage(`Failed to spawn Python: ${errorMsg}`);
      return null;
    }
  }

  /**
   * Send a JSON message to a Python process
   */
  sendMessage(process: ChildProcess, message: any): void {
    try {
      const jsonMessage = JSON.stringify(message) + '\n';
      this.outputChannel.appendLine(`Sending: ${jsonMessage.trim()}`);
      process.stdin?.write(jsonMessage);
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      this.outputChannel.appendLine(`Failed to send message: ${errorMsg}`);
    }
  }

  /**
   * Register a message handler for a Python process
   */
  onMessage(process: ChildProcess, handler: (message: any) => void): void {
    // Find the process ID
    for (const [id, proc] of this.processes.entries()) {
      if (proc === process) {
        this.messageHandlers.set(id, handler);
        break;
      }
    }
  }

  /**
   * Terminate a Python process
   */
  terminate(process: ChildProcess): void {
    process.kill('SIGTERM');
  }

  /**
   * Terminate all Python processes
   */
  terminateAll(): void {
    for (const process of this.processes.values()) {
      process.kill('SIGTERM');
    }
    this.processes.clear();
    this.messageHandlers.clear();
  }

  /**
   * Get all active processes
   */
  getActiveProcesses(): ChildProcess[] {
    return Array.from(this.processes.values());
  }
}
