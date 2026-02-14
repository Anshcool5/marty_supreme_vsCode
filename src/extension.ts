import * as vscode from "vscode";
import { PythonProcessManager } from "./python/processManager";
import * as path from "path";
import { ChildProcess } from "child_process";

export function activate(context: vscode.ExtensionContext) {
  console.log("Marty Supreme extension is now active!");

  // Create output channel for logging
  const outputChannel = vscode.window.createOutputChannel("Marty Supreme");
  outputChannel.appendLine("Marty Supreme extension activated!");
  const pythonManager = new PythonProcessManager(context, outputChannel);
  let activePongProcess: ChildProcess | undefined;

  const startPongIfNotRunning = async (): Promise<{
    started: boolean;
    message: string;
  }> => {
    if (
      activePongProcess &&
      activePongProcess.exitCode === null &&
      !activePongProcess.killed
    ) {
      return { started: false, message: "Pong already running." };
    }

    try {
      const gameScriptPath = path.join(
        context.extensionPath,
        "python",
        "games",
        "hand_server.py"
      );

      const process = await pythonManager.spawn(gameScriptPath, [
        "--run-pong",
        "--show-preview",
      ]);

      if (!process) {
        return {
          started: false,
          message: "Failed to launch Pong. Check Output > Marty Supreme.",
        };
      }

      activePongProcess = process;
      activePongProcess.on("exit", (code) => {
        outputChannel.appendLine(`Pong process exited with code ${code}`);
        activePongProcess = undefined;
      });

      return { started: true, message: "Pong launched successfully." };
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : "Unknown error occurred";
      outputChannel.appendLine(`Failed to launch Pong: ${errorMsg}`);
      return {
        started: false,
        message: `Failed to launch Pong: ${errorMsg}. Check Output > Marty Supreme.`,
      };
    }
  };

  // Register hello command
  const helloCommand = vscode.commands.registerCommand(
    "marty-supreme.hello",
    () => {
      vscode.window.showInformationMessage("Hello from Marty Supreme! 🏓");
      outputChannel.appendLine("Hello command executed");
    }
  );

  // Register example game command
  const exampleGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runExampleGame",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting example game...");

      try {
        // Path to example game script
        const gameScriptPath = path.join(
          context.extensionPath,
          "python",
          "games",
          "example_game.py"
        );

        // Spawn the Python process
        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine("Example game started successfully!");
          vscode.window.showInformationMessage(
            "Marty Supreme: Example game is running!"
          );

          // Send initialization command
          pythonManager.sendMessage(process, {
            command: "initialize",
            data: { message: "Hello from VSCode!" },
          });

          // Set up message handler
          pythonManager.onMessage(process, (message) => {
            outputChannel.appendLine(
              `Game response: ${JSON.stringify(message)}`
            );

            if (message.type === "state_update") {
              vscode.window.showInformationMessage(
                `Game State: ${JSON.stringify(message.state)}`
              );
            }
          });

          // Clean up on process exit
          process.on("exit", (code) => {
            outputChannel.appendLine(`Game process exited with code ${code}`);
            vscode.window.showInformationMessage("Game ended!");
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error occurred";
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start game: ${errorMsg}`);
      }
    }
  );

  // Register Tetris game command
  const tetrisGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runTetris",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting Tetris 1926...");

      try {
        const gameScriptPath = path.join(
          context.extensionPath,
          "python",
          "games",
          "tetris.py"
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine("Tetris 1926 started successfully!");
          vscode.window.showInformationMessage(
            "Marty Supreme: Tetris 1926 is running!"
          );

          process.on("exit", (code) => {
            outputChannel.appendLine(`Tetris process exited with code ${code}`);
            vscode.window.showInformationMessage("Tetris 1926 ended.");
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error occurred";
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Tetris: ${errorMsg}`);
      }
    }
  );

  // Register Blackjack game command
  const blackjackGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runBlackjack",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting Blackjack 1940s...");

      try {
        const gameScriptPath = path.join(
          context.extensionPath,
          "python",
          "games",
          "blackjack.py"
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine("Blackjack 1940s started successfully!");
          vscode.window.showInformationMessage(
            "Marty Supreme: Blackjack 1940s is running!"
          );

          process.on("exit", (code) => {
            outputChannel.appendLine(
              `Blackjack process exited with code ${code}`
            );
            vscode.window.showInformationMessage("Blackjack 1940s ended.");
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error occurred";
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(
          `Failed to start Blackjack: ${errorMsg}`
        );
      }
    }
  );

  // Register Pong game command (hand-tracked)
  const pongGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runPong",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting Pong 1950 (hand tracking)...");

      const result = await startPongIfNotRunning();
      if (result.started) {
        outputChannel.appendLine("Pong 1950 started successfully!");
        vscode.window.showInformationMessage(
          "Marty Supreme: Pong 1950 is running!"
        );
      } else {
        outputChannel.appendLine(result.message);
        vscode.window.showWarningMessage(result.message);
      }
    }
  );

  const chatApi = (vscode as any).chat;
  if (chatApi?.createChatParticipant) {
    const martyParticipant = chatApi.createChatParticipant(
      "marty.agent",
      async (request: any, _ctx: any, stream: any) => {
        outputChannel.show(true);
        const result = await startPongIfNotRunning();
        stream.markdown(result.message);

        const prompt =
          typeof request?.prompt === "string" ? request.prompt.trim() : "";
        if (prompt) {
          stream.markdown(`Prompt: ${prompt}`);
        }

        return { metadata: { started: result.started } };
      }
    );
    context.subscriptions.push(martyParticipant);
    outputChannel.appendLine("Chat participant registered: @marty");
  } else {
    outputChannel.appendLine(
      "Chat Participant API not available in this VS Code build."
    );
  }

  // Register Slot Machine game command
  const slotMachineGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runSlotMachine",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting Slot Machine 1950s Vegas...");

      try {
        const pythonManager = new PythonProcessManager(context, outputChannel);

        const gameScriptPath = path.join(
          context.extensionPath,
          "python",
          "games",
          "slot_machine.py"
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine("Slot Machine 1950s started successfully!");
          vscode.window.showInformationMessage(
            "Marty Supreme: Pull your fist down to spin the slots!"
          );

          process.on("exit", (code) => {
            outputChannel.appendLine(
              `Slot Machine process exited with code ${code}`
            );
            vscode.window.showInformationMessage("Slot Machine 1950s ended.");
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error occurred";
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(
          `Failed to start Slot Machine: ${errorMsg}`
        );
      }
    }
  );

  // Register Ninja game command
  const ninjaGameCommand = vscode.commands.registerCommand(
    "marty-supreme.runNinja",
    async () => {
      outputChannel.show();
      outputChannel.appendLine("Starting Fruit Slayer Ninja...");

      try {
        const gameScriptPath = path.join(
          context.extensionPath,
          "python",
          "games",
          "ninja.py"
        );

        const process = await pythonManager.spawn(gameScriptPath);

        if (process) {
          outputChannel.appendLine("Fruit Slayer Ninja started successfully!");
          vscode.window.showInformationMessage(
            "Marty Supreme: Fruit Slayer Ninja is running!"
          );

          process.on("exit", (code) => {
            outputChannel.appendLine(`Ninja process exited with code ${code}`);
            vscode.window.showInformationMessage("Fruit Slayer Ninja ended.");
          });
        }
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "Unknown error occurred";
        outputChannel.appendLine(`Error: ${errorMsg}`);
        vscode.window.showErrorMessage(`Failed to start Ninja: ${errorMsg}`);
      }
    }
  );

  // Add commands to subscriptions
  context.subscriptions.push(helloCommand);
  context.subscriptions.push(exampleGameCommand);
  context.subscriptions.push(tetrisGameCommand);
  context.subscriptions.push(blackjackGameCommand);
  context.subscriptions.push(pongGameCommand);
  context.subscriptions.push(
    new vscode.Disposable(() => {
      if (activePongProcess && activePongProcess.exitCode === null) {
        pythonManager.terminate(activePongProcess);
      }
    })
  );
  context.subscriptions.push(slotMachineGameCommand);
  context.subscriptions.push(ninjaGameCommand);
  context.subscriptions.push(outputChannel);

  // Show welcome message
  vscode.window.showInformationMessage(
    "Marty Supreme is ready! Relive your Marty Supreme moment! 🏓"
  );
}

export function deactivate() {
  console.log("Marty Supreme extension is now deactivated");
}
