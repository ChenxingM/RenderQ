# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RenderQ is a lightweight render queue management system designed for small animation/VFX teams. It provides distributed rendering job management with support for After Effects (and extensible to other renderers).

## Common Commands

### Development Setup
```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -e ".[all]"
```

### Running Components
```bash
# Start server (scheduler + API)
python -m src.server.main
# or: uvicorn src.server.main:app --host 0.0.0.0 --port 8000

# Start worker agent
python -m src.worker.agent --server http://localhost:8000

# Start GUI
python -m src.client.gui.main

# CLI usage
renderq submit -p aftereffects -n "Job Name" --project "path.aep" --comp "Comp1" --output "out_[#####].exr"
renderq jobs
renderq workers
```

### Testing & Linting
```bash
pytest                    # Run all tests
pytest tests/test_foo.py  # Run single test file
black .                   # Format code
ruff check .              # Lint
```

## Architecture

The system follows a distributed architecture with four main components:

```
Server (FastAPI)      Worker Agent          GUI/CLI
     │                     │                   │
     └──────── API ────────┴───────────────────┘
               │
          SQLite DB
```

### Directory Structure
```
src/
├── core/           # Shared core library
│   ├── models.py   # Pydantic models (Job, Task, Worker)
│   ├── database.py # SQLite wrapper
│   ├── scheduler.py# Async task scheduler
│   └── events.py   # EventBus pub/sub
├── plugins/        # Render plugins
│   ├── base.py     # RenderPlugin ABC
│   ├── aftereffects.py
│   └── registry.py # Plugin registry
├── server/         # FastAPI server
│   └── main.py
├── worker/         # Worker agent
│   └── agent.py
└── client/         # Client applications
    ├── gui/        # PySide6 GUI
    │   ├── main.py
    │   ├── main_window.py
    │   └── widgets/
    └── cli/        # Command line tool
        └── renderq.py
```

### Data Flow
1. Job submitted via API/CLI/GUI → stored in DB as PENDING
2. Scheduler picks up PENDING jobs → validates via plugin → creates Tasks → status becomes QUEUED
3. Worker polls `/api/workers/{id}/request-task` → gets assigned Task → status becomes ACTIVE
4. Worker executes command, reports progress → on completion updates Task status
5. Scheduler aggregates Task results → updates Job progress/status

### Plugin System (`src/plugins/`)
- **base.py**: `RenderPlugin` ABC defining `validate()`, `create_tasks()`, `build_command()`, `parse_progress()`
- **aftereffects.py**: AE implementation with aerender command building, chunk rendering support
- **registry.py**: Singleton PluginRegistry for plugin discovery and access

To add a new renderer:
1. Create `src/plugins/myrenderer.py` inheriting from `CommandLinePlugin`
2. Implement required methods
3. Export a `plugin` instance at module level
4. Add to `load_builtin_plugins()` in registry.py

### Server (`src/server/main.py`)
FastAPI app with:
- REST endpoints for Jobs, Tasks, Workers CRUD
- WebSocket endpoint (`/ws`) for real-time updates
- Scheduler started on app lifespan

### Worker (`src/worker/agent.py`)
Async agent that:
- Registers with server
- Sends periodic heartbeats
- Polls for tasks
- Executes subprocess commands
- Parses stdout for progress
- Reports results back to server

### Client (`src/client/`)
- **gui/**: PySide6 application with job/worker tables, auto-refresh timer
- **cli/**: Typer-based CLI with rich output

## Key Patterns

- **Singleton pattern**: EventBus, PluginRegistry, Database connections per thread
- **Status state machines**: Jobs flow PENDING → QUEUED → ACTIVE → COMPLETED/FAILED; Tasks flow PENDING → ASSIGNED → RUNNING → COMPLETED/FAILED
- **Pydantic models** for API request/response validation
- **Async/await** throughout scheduler and worker for concurrent operations
