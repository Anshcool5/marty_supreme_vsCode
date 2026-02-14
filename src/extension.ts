import * as vscode from 'vscode';
import { PythonProcessManager } from './python/processManager';
import * as path from 'path';

export function activate(context: vscode.ExtensionContext) {
  console.log('Marty Supreme extension is now active!');

  // Create output channel for logging
  const outputChannel = vscode.window.createOutputChannel('Marty Supreme');
  outputChannel.appendLine('Marty Supreme extension activated!');

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

  // Add commands to subscriptions
  context.subscriptions.push(helloCommand);
  context.subscriptions.push(exampleGameCommand);
  context.subscriptions.push(outputChannel);

  // Show welcome message
  vscode.window.showInformationMessage(
    'Marty Supreme is ready! Relive your Marty Supreme moment! 🏓'
  );
}

export function deactivate() {
  console.log('Marty Supreme extension is now deactivated');
}
