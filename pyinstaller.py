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
    "-i",
    "./favicon.ico",
    "--onefile",
    # Add nicegui data
    "--collect-all", "nicegui",
    "--collect-all", "pydantic",
    "--collect-all", "burr",
    # Add local source code directories
    "--add-data", f"{project_root / 'actions'}{os.pathsep}actions",
    "--add-data", f"{project_root / 'graphs'}{os.pathsep}graphs",
    "--add-data", f"{project_root / 'utils'}{os.pathsep}utils",
    "--add-data", f"{project_root / 'logger.py'}{os.pathsep}.",
    # "--add-data", f"{project_root}{os.pathsep}.",
    # Add .env file
    "--add-data", f"{project_root / '.env'}{os.pathsep}.",
    "--exclude-module", "ruff",
    "--exclude-module", "ipython",
    "--exclude-module", "mypy",
    "--exclude-module", "pytest",
    "--exclude-module", "ruff",
    "--exclude-module", "flake8",
    "--exclude-module", "build",
    "--exclude-module", "twine",
    "--exclude-module", "pre-commit",
]
subprocess.call(cmd)
