import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as path from 'path';
import * as os from 'os';

function pythonCandidatesFromPrefix(prefix: string): string[] {
  if (!prefix) {
    return [];
  }
  return [
    path.join(prefix, 'bin', 'python'),
    path.join(prefix, 'bin', 'python3'),
    path.join(prefix, 'Scripts', 'python.exe'),
  ];
}

function normalizeInterpreterPath(
  rawPath: string,
  context: vscode.ExtensionContext
): string {
  let normalized = rawPath.trim();
  if (!normalized) {
    return '';
  }

  normalized = normalized.replace(
    /\$\{workspaceFolder\}/g,
    context.extensionPath
  );

  if (normalized.startsWith('~/')) {
    normalized = path.join(os.homedir(), normalized.slice(2));
  }

  if (!path.isAbsolute(normalized)) {
    normalized = path.join(context.extensionPath, normalized);
  }

  return normalized;
}

export async function resolvePythonInterpreter(
  context: vscode.ExtensionContext,
  output?: vscode.OutputChannel
): Promise<string> {
  const candidates: string[] = [];
  const seen = new Set<string>();
  const addCandidate = (candidate: string) => {
    if (!candidate) {
      return;
    }
    if (!seen.has(candidate)) {
      seen.add(candidate);
      candidates.push(candidate);
    }
  };

  const configuredInterpreter = vscode.workspace
    .getConfiguration('python')
    .get<string>('defaultInterpreterPath');
  if (configuredInterpreter) {
    addCandidate(normalizeInterpreterPath(configuredInterpreter, context));
  }

  addCandidate(process.env.MARTY_SUPREME_PYTHON ?? '');

  for (const envPrefix of [
    process.env.VIRTUAL_ENV,
    process.env.CONDA_PREFIX,
    process.env.PYENV_VIRTUAL_ENV,
  ]) {
    for (const candidate of pythonCandidatesFromPrefix(envPrefix ?? '')) {
      addCandidate(candidate);
    }
  }

  for (const localPrefix of [
    path.join(context.extensionPath, 'python', 'venv'),
    path.join(context.extensionPath, 'python', '.venv'),
    path.join(context.extensionPath, 'venv'),
    path.join(context.extensionPath, '.venv'),
  ]) {
    for (const candidate of pythonCandidatesFromPrefix(localPrefix)) {
      addCandidate(candidate);
    }
  }

  for (const commandCandidate of ['python3', 'python', 'py']) {
    addCandidate(commandCandidate);
  }

  for (const candidate of candidates) {
    const available = await new Promise<boolean>((resolve) => {
      const probe = spawn(candidate, ['--version']);
      probe.on('error', () => resolve(false));
      probe.on('exit', (code) => resolve(code === 0));
    });

    if (available) {
      output?.appendLine(`Using Python interpreter: ${candidate}`);
      return candidate;
    }
  }

  throw new Error(
    'No usable Python interpreter found. Configure python.defaultInterpreterPath or install Python 3.8+.'
  );
}
