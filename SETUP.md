# Marty Supreme VSCode Extension - Setup Guide

Complete setup instructions for Windows and macOS to get the Marty Supreme extension running.

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

### Required for Both Platforms
- **Visual Studio Code** (version 1.85.0 or higher)
  - Download: https://code.visualstudio.com/
- **Node.js** (version 18.x or higher)
  - Download: https://nodejs.org/
- **Python** (version 3.8 or higher)
  - Download: https://www.python.org/downloads/

### Optional (for Computer Vision Features)
- **Git** (for version control)
  - Windows: https://git-scm.com/download/win
  - macOS: Usually pre-installed, or install via Xcode Command Line Tools

---

## 🪟 Windows Setup

### Step 1: Install Prerequisites

#### Install Node.js
1. Download Node.js from https://nodejs.org/
2. Run the installer (.msi file)
3. Follow the installation wizard (use default settings)
4. Verify installation:
   ```cmd
   node --version
   npm --version
   ```

#### Install Python
1. Download Python from https://www.python.org/downloads/
2. **IMPORTANT**: Check "Add Python to PATH" during installation
3. Run the installer
4. Verify installation:
   ```cmd
   python --version
   ```
   Or try:
   ```cmd
   py --version
   ```

### Step 2: Clone/Open the Project

1. Open Command Prompt or PowerShell
2. Navigate to the project directory:
   ```cmd
   cd C:\Users\YourUsername\Documents\Projects\marty_supreme_vsCode
   ```

### Step 3: Install Node Dependencies

```cmd
npm install
```

This will install:
- TypeScript
- esbuild
- VSCode type definitions

### Step 4: Install Python Dependencies (Optional)

For computer vision features:

```cmd
cd python
pip install -r requirements.txt
```

Or if using `py` launcher:
```cmd
cd python
py -m pip install -r requirements.txt
```

This installs:
- `opencv-python` (Computer Vision)
- `numpy` (Array operations)

### Step 5: Build the Extension

Return to project root and compile:
```cmd
cd ..
npm run compile
```

You should see output indicating the build succeeded.

### Step 6: Test the Extension

1. Open the project in Visual Studio Code:
   ```cmd
   code .
   ```

2. Press **F5** to launch the Extension Development Host
   - A new VSCode window will open with `[Extension Development Host]` in the title

3. In the Extension Development Host window:
   - Press **Ctrl+Shift+P** to open Command Palette
   - Type "Marty Supreme" to see available commands
   - Try "Marty Supreme: Hello World"

### Troubleshooting (Windows)

**Python not found:**
- Make sure Python is in your PATH
- Try using `py` instead of `python` command
- Restart Command Prompt/PowerShell after Python installation

**npm install fails:**
- Run Command Prompt as Administrator
- Clear npm cache: `npm cache clean --force`
- Delete `node_modules` and `package-lock.json`, then run `npm install` again

**Build fails:**
- Make sure you're in the project root directory
- Check Node.js version: `node --version` (should be 18+)

---

## 🍎 macOS Setup

### Step 1: Install Prerequisites

#### Install Xcode Command Line Tools (if not already installed)
```bash
xcode-select --install
```

#### Install Homebrew (Package Manager)
If you don't have Homebrew:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Install Node.js
Using Homebrew:
```bash
brew install node
```

Or download directly from https://nodejs.org/

Verify installation:
```bash
node --version
npm --version
```

#### Install Python
macOS usually comes with Python, but install Python 3:

Using Homebrew:
```bash
brew install python3
```

Verify installation:
```bash
python3 --version
```

### Step 2: Clone/Open the Project

1. Open Terminal
2. Navigate to the project directory:
   ```bash
   cd ~/Documents/Projects/marty_supreme_vsCode
   ```

### Step 3: Install Node Dependencies

```bash
npm install
```

This will install:
- TypeScript
- esbuild
- VSCode type definitions

### Step 4: Install Python Dependencies (Optional)

For computer vision features:

```bash
cd python
pip3 install -r requirements.txt
```

Or if you prefer virtual environment (recommended):
```bash
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This installs:
- `opencv-python` (Computer Vision)
- `numpy` (Array operations)

### Step 5: Build the Extension

Return to project root and compile:
```bash
cd ..
npm run compile
```

You should see output indicating the build succeeded.

### Step 6: Test the Extension

1. Open the project in Visual Studio Code:
   ```bash
   code .
   ```

2. Press **F5** (or **fn+F5** on some MacBooks) to launch the Extension Development Host
   - A new VSCode window will open with `[Extension Development Host]` in the title

3. In the Extension Development Host window:
   - Press **Cmd+Shift+P** to open Command Palette
   - Type "Marty Supreme" to see available commands
   - Try "Marty Supreme: Hello World"

### Troubleshooting (macOS)

**Python not found:**
- Use `python3` instead of `python`
- Make sure Python 3 is installed: `brew install python3`

**Permission errors during pip install:**
- Use `pip3 install --user -r requirements.txt`
- Or create a virtual environment (see Step 4)

**npm install fails:**
- Clear npm cache: `npm cache clean --force`
- Check permissions on the project directory
- Try using `sudo npm install` (not recommended, but may work)

**F5 doesn't work:**
- Try **fn+F5** (function key might be needed)
- Or use Run → Start Debugging from the menu

---

## 🚀 Development Workflow

### Watch Mode (Auto-Rebuild)

Start watch mode to automatically rebuild when you make changes:

**Windows:**
```cmd
npm run watch
```

**macOS:**
```bash
npm run watch
```

### Testing Your Changes

1. Make changes to TypeScript or Python files
2. If not in watch mode, run: `npm run compile`
3. In the Extension Development Host window, press:
   - **Windows**: **Ctrl+R**
   - **macOS**: **Cmd+R**
4. Test your changes

### Viewing Extension Output

1. In the Extension Development Host window:
   - **Windows**: **Ctrl+Shift+U** (or View → Output)
   - **macOS**: **Cmd+Shift+U** (or View → Output)
2. Select "Marty Supreme" from the dropdown on the right
3. See all logs, Python output, and debug information

---

## 🤖 Agent Mode MCP Setup (Codex)

Use this if you want agent mode to launch/check/stop Pong through tools instead of chat mentions.

### Important for Collaborators

- `mcp/` source files are committed to git.
- `mcp/node_modules` is **not** committed.
- Every collaborator must run dependency install locally.

### Step 1: Install MCP Dependencies

From repo root:

**Windows (PowerShell/CMD):**
```cmd
npm --prefix mcp install
```

**macOS/Linux:**
```bash
npm --prefix mcp install
```

### Step 2: Build MCP Server

From repo root:

**Windows:**
```cmd
npm run mcp:build
```

**macOS/Linux:**
```bash
npm run mcp:build
```

This creates:

- `mcp/dist/server.js`

### Step 3: Register MCP Server in Codex

Edit:

- `~/.codex/config.toml`

Add:

```toml
[mcp_servers.marty_pong]
command = "node"
args = ["/ABSOLUTE/PATH/TO/marty_supreme_vsCode/mcp/dist/server.js"]
```

Example on this project:

```toml
[mcp_servers.marty_pong]
command = "node"
args = ["/Users/siddharthdileep/silicon/marty_supreme_vsCode/mcp/dist/server.js"]
```

Then restart Codex/session so MCP config is reloaded.

### Step 4: Verify MCP Tools Are Available

Expected tools:

- `launch_pong(showPreview?: boolean)`
- `pong_status()`
- `stop_pong(force?: boolean)`

Quick validation flow in agent mode:

1. Call `launch_pong` (expect `launched`).
2. Call `launch_pong` again (expect `already_running`).
3. Call `pong_status` (expect `running` with pid).
4. Call `stop_pong` (expect `stopped`).
5. Call `pong_status` again (expect `not_running`).

### Troubleshooting MCP

**`server.js` not found**
- Re-run `npm run mcp:build`.
- Confirm file exists: `mcp/dist/server.js`.

**Module not found (`@modelcontextprotocol/sdk`)**
- Run `npm --prefix mcp install`.

**Node not found**
- Check `node --version` (Node 18+ required).

**Pong launch fails**
- Ensure Python deps are installed in your environment (`opencv-python`, `mediapipe`, `pygame`).
- Verify script path exists: `python/games/hand_server.py`.
- Grant camera permission to terminal/VS Code host.

---

## 🤖 Claude Code MCP Setup

Use this to enable the Pong MCP server in Claude Code (Anthropic's VS Code extension).

### Prerequisites

- Claude Code extension installed in VS Code
- MCP server built (see "Agent Mode MCP Setup" section above)
- Node.js 18+ available in PATH

### Configuration Options

Claude Code supports MCP servers at three scopes:

1. **User scope** (`~/.claude.json`) - Available across all your projects
2. **Project scope** (`.mcp.json` in project root) - Shared with team via git
3. **Local scope** (`~/.claude.json` with project path) - Project-specific, not shared

### Option 1: User-Scoped Setup (Recommended for Personal Use)

Add the MCP server to your global Claude Code configuration:

**Windows (PowerShell/CMD):**
```cmd
claude mcp add --scope user --transport stdio marty-pong -- node C:/Users/YourUsername/Documents/Projects/marty_supreme_vsCode/mcp/dist/server.js
```

**macOS/Linux:**
```bash
claude mcp add --scope user --transport stdio marty-pong -- node /Users/yourusername/Documents/Projects/marty_supreme_vsCode/mcp/dist/server.js
```

This updates `~/.claude.json` and makes the MCP server available in all workspaces.

### Option 2: Project-Scoped Setup (Recommended for Teams)

Create `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "marty-pong": {
      "command": "node",
      "args": [
        "C:/Users/YourUsername/Documents/Projects/marty_supreme_vsCode/mcp/dist/server.js"
      ],
      "env": {}
    }
  }
}
```

**Important:** Use absolute paths, and replace `YourUsername` with your actual username.

### Verifying Installation

1. **Restart VS Code** to load the new MCP configuration

2. **Check MCP server status** in Claude Code chat:
   ```
   /mcp
   ```

3. **List configured servers:**
   ```cmd
   claude mcp list
   ```

4. **Test the tools** - In Claude Code chat, try:
   ```
   launch pong
   ```

### Available MCP Tools

Once configured, Claude Code can use these tools:

- **`launch_pong(showPreview?: boolean)`** - Launch the Pong game
  - Returns: `{status: "launched" | "already_running" | "error", message: string, pid?: number}`

- **`pong_status()`** - Check if Pong is running
  - Returns: `{status: "running" | "not_running", pid?: number}`

- **`stop_pong(force?: boolean)`** - Stop the Pong game
  - Returns: `{status: "stopped" | "not_running" | "error", message: string}`

### Example Usage

In Claude Code chat:

```
User: "Launch pong with preview"
Claude: *uses launch_pong(showPreview: true) tool*

User: "Is pong running?"
Claude: *uses pong_status() tool*

User: "Stop the game"
Claude: *uses stop_pong() tool*
```

### Windows-Specific Fix

The MCP server has been updated to use `python` instead of `python3` on Windows. If you cloned an older version, update `mcp/src/server.ts`:

```typescript
// Change this:
return "python3";

// To this:
return "python";
```

Then rebuild:
```cmd
npm run mcp:build
```

### Troubleshooting Claude Code MCP

**MCP server not appearing:**
- Restart VS Code completely (File → Exit, then reopen)
- Run `claude mcp list` to verify configuration
- Check for typos in the MCP server path

**"No MCP servers found":**
- Ensure `.mcp.json` is in the project root OR the server is in `~/.claude.json`
- Verify the MCP server file exists: `mcp/dist/server.js`
- Check that Node.js is in your PATH: `node --version`

**Pong launches but window doesn't appear:**
- Check your taskbar - the window might be hidden
- Use Alt+Tab (Windows) or Cmd+Tab (macOS) to find the window
- The game requires webcam access - grant permissions if prompted

**"python not found" error:**
- On Windows, ensure Python is in PATH
- The MCP server uses `python` command (not `python3`)
- Test: `python --version` should work

**Module not found errors:**
- Re-install MCP dependencies: `npm --prefix mcp install`
- Rebuild the server: `npm run mcp:build`

**Permission denied:**
- On first use, Claude Code will prompt you to approve the MCP server
- Click "Allow" to enable the tools

### Managing MCP Servers

**List all servers:**
```bash
claude mcp list
```

**Get details for a specific server:**
```bash
claude mcp get marty-pong
```

**Remove a server:**
```bash
claude mcp remove marty-pong
```

**Reset project-scoped approvals:**
```bash
claude mcp reset-project-choices
```

### Security Note

- **Project-scoped servers** (`.mcp.json`) require approval on first use
- This prevents malicious projects from running arbitrary code
- You'll see a prompt asking to approve the server - click "Allow" if you trust the project

---

## 📦 Project Structure

```
marty_supreme_vsCode/
├── mcp/
│   ├── src/
│   │   └── server.ts        # MCP server source
│   ├── dist/                # Built MCP server output (auto-generated)
│   ├── package.json         # MCP package manifest
│   └── README.md            # MCP-specific docs
├── .vscode/
│   ├── launch.json          # Debug configuration
│   └── tasks.json           # Build tasks
├── src/
│   ├── extension.ts         # Main extension entry point
│   └── python/
│       └── processManager.ts # Python subprocess manager
├── python/
│   ├── lib/
│   │   └── game_base.py     # Base class for Python games
│   ├── games/
│   │   └── example_game.py  # Example game
│   └── requirements.txt     # Python dependencies
├── dist/                    # Compiled extension (auto-generated)
├── package.json             # Extension manifest
└── tsconfig.json            # TypeScript configuration
```

---

## 🎮 Available Commands

Open Command Palette (**Ctrl+Shift+P** on Windows, **Cmd+Shift+P** on macOS):

1. **Marty Supreme: Hello World**
   - Simple test command
   - Shows a notification message

2. **Marty Supreme: Run Example Game**
   - Demonstrates Python integration
   - Spawns a Python subprocess
   - Shows communication between extension and Python

3. **Marty Supreme: Run Pong 1950 (Hand Tracking)**
   - Launches Pong directly from the extension

---

## 🧪 Testing Python Integration

### Test if Python is Detected

1. Run "Marty Supreme: Run Example Game"
2. Open Output panel (select "Marty Supreme")
3. You should see:
   ```
   Found Python: python3
   Spawning Python process: python3 ...
   INFO: Game started, waiting for commands...
   ```

### What the Example Game Does

- Accepts JSON commands from the extension
- Demonstrates computer vision setup (if OpenCV installed)
- Returns game state updates
- Shows full communication pipeline

---

## 🔧 Common Issues & Solutions

### Issue: "Python not found"

**Windows:**
```cmd
# Check if Python is in PATH
where python
where py

# If not found, reinstall Python with "Add to PATH" checked
```

**macOS:**
```bash
# Check if Python is installed
which python3

# Install if missing
brew install python3
```

### Issue: "Cannot find module 'vscode'"

This is normal - VSCode provides this module at runtime. The extension will work when you press F5.

### Issue: Build fails with esbuild errors

```bash
# Clear everything and reinstall
rm -rf node_modules package-lock.json dist out
npm install
npm run compile
```

### Issue: Python packages not found

**Install in your Python environment:**

Windows:
```cmd
cd python
pip install opencv-python numpy
```

macOS:
```bash
cd python
pip3 install opencv-python numpy
```

---

## 📚 Next Steps

1. ✅ **Press F5** to test the extension
2. ✅ **Try the example commands** in Command Palette
3. ✅ **Check the output logs** to see Python communication
4. 🎮 **Start building your games** in `python/games/`
5. 🏓 **Good luck with the hackathon!**

---

## 🆘 Getting Help

If you encounter issues:

1. Check the Output panel in VSCode (select "Marty Supreme")
2. Check the Debug Console for TypeScript errors
3. Verify all prerequisites are installed with correct versions
4. Make sure you're running commands from the project root directory

---

## 📝 Additional Resources

- [VSCode Extension API](https://code.visualstudio.com/api)
- [Python subprocess module](https://docs.python.org/3/library/subprocess.html)
- [OpenCV Python Tutorial](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)

---

**Happy Coding! 🚀**
