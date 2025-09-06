import subprocess
import os
from pathlib import Path

import nicegui

# Get the project root directory
project_root = Path(__file__).parent

cmd = [
    "python",
    "-m",
    "PyInstaller",
    "web_chat.py",
    "--name",
    "web_chat",
    "--onefile",
    # Add nicegui data
    "--collect-all", "nicegui",
    "--collect-all", "pydantic",
    "--collect-all", "burr",
    # Add local source code directories
    "--add-data", f"{project_root}{os.pathsep}.", # Add logger.py to the root of the bundle
    # Add .env file
    "--add-data", f"{project_root / '.env'}{os.pathsep}.", # New: Add .env file
    # "--exclude-module",
    # "ruff",
    # Add hidden imports for pydantic
    # "--hidden-import", "pydantic",
    # "--hidden-import", "pydantic.main",
    # "--hidden-import", "pydantic_core",
    # "--hidden-import", "pydantic.deprecated.decorator",
    # "--hidden-import", "pydantic.dataclasses",
    # "--hidden-import", "pydantic.json_schema",
]
subprocess.call(cmd)
