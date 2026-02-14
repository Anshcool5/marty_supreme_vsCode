# 🏓 Marty Supreme - VSCode Extension

**Official submission for the UAIS SillyCon Valley Hackathon 2026**

Relive your Marty Supreme moment as you wait for your CLI prompt with some exclusive motivation ;)

---

## 🎯 What is Marty Supreme?

A VSCode extension that brings Python-powered games with computer vision capabilities right into your development environment. Built with TypeScript for the extension frontend and Python for game backends, all communicating seamlessly without any servers.

## ✨ Features

- 🎮 **Python-Powered Games** - Build game backends in Python with full computer vision support
- 👁️ **Computer Vision Ready** - Integrated OpenCV and NumPy for CV-based games
- 🚀 **No Servers Required** - Simple subprocess communication via stdin/stdout
- 🔧 **Easy to Extend** - Add new games by creating Python files
- 📦 **Self-Contained** - Everything bundled in one extension

## 🚀 Quick Start

### Prerequisites
- Visual Studio Code 1.85.0+
- Node.js 18+
- Python 3.8+

### Installation

```bash
# Install Node dependencies
npm install

# Install Python dependencies (optional, for computer vision)
cd python
pip install -r requirements.txt
cd ..

# Build the extension
npm run compile
```

### Run the Extension

1. Press **F5** in VSCode to launch Extension Development Host
2. In the new window, press **Ctrl+Shift+P** (or **Cmd+Shift+P** on Mac)
3. Type "Marty Supreme" and try the commands!

📖 **For detailed setup instructions, see [SETUP.md](SETUP.md)**

## 🎮 Available Commands

- **Marty Supreme: Hello World** - Test the extension
- **Marty Supreme: Run Example Game** - Test Python integration with example game

## 🏗️ Architecture

```
TypeScript Extension (VSCode)
         ↓ (stdin/stdout JSON)
Python Game Backend
         ↓
Computer Vision (OpenCV)
```

### Key Components

- **Extension** ([src/extension.ts](src/extension.ts)) - Main VSCode extension logic
- **Process Manager** ([src/python/processManager.ts](src/python/processManager.ts)) - Handles Python subprocess lifecycle
- **Game Base Class** ([python/lib/game_base.py](python/lib/game_base.py)) - Abstract base for all Python games
- **Example Game** ([python/games/example_game.py](python/games/example_game.py)) - Template showing full pipeline

## 🎨 Adding New Games

1. Create a new Python file in `python/games/`:
   ```python
   from lib.game_base import GameBase

   class MyGame(GameBase):
       def initialize(self, config):
           return {'status': 'ready'}

       def process_input(self, input_data):
           # Your game logic
           return {'result': 'ok'}

       def get_state(self):
           return {'score': 0}

       def cleanup(self):
           pass
   ```

2. Add a command in `src/extension.ts`
3. Register the command in `package.json`

## 🛠️ Development

```bash
# Start watch mode (auto-rebuild)
npm run watch

# Build for production
npm run compile

# Press F5 to test
# Press Ctrl+R (or Cmd+R) in Extension Development Host to reload
```

## 📁 Project Structure

```
marty_supreme_vsCode/
├── src/                    # TypeScript source
│   ├── extension.ts        # Main extension
│   └── python/             # Python integration
├── python/                 # Python games
│   ├── lib/                # Base classes
│   └── games/              # Game implementations
├── dist/                   # Compiled extension
└── package.json            # Extension manifest
```

## 🧪 Testing

1. **Basic Test**: Run "Marty Supreme: Hello World"
2. **Python Test**: Run "Marty Supreme: Run Example Game"
3. **View Logs**: Open Output panel → Select "Marty Supreme"

## 📝 Communication Protocol

Extension ↔ Python communication uses line-delimited JSON:

**Extension → Python:**
```json
{"command": "initialize", "data": {"config": "value"}}
```

**Python → Extension:**
```json
{"type": "state_update", "status": "ok", "state": {"score": 10}}
```

## 🎓 Technologies Used

- **TypeScript** - Extension development
- **Python 3** - Game backends
- **OpenCV** - Computer vision
- **esbuild** - Fast bundling
- **VSCode Extension API** - IDE integration

## 📚 Documentation

- **[SETUP.md](SETUP.md)** - Detailed setup instructions for Windows and macOS
- **[Implementation Plan](C:\Users\prana\.claude\plans\noble-napping-quilt.md)** - Technical design document

## 🤝 Contributing

This is a hackathon project! Feel free to:
- Add new games in `python/games/`
- Enhance the communication protocol
- Add computer vision features
- Improve the UI/UX

## 📄 License

Created for UAIS SillyCon Valley Hackathon 2026

---

**Built with ❤️ for the hackathon. Now go relive your Marty Supreme moment! 🏓**
