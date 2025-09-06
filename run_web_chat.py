#!/usr/bin/env python3
"""
Startup script for the Burr Agent Web Chat interface.
This script provides a simple way to run the web chat with proper configuration.
"""

import os
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Run Burr Agent Web Chat')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to (default: 8080)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    
    args = parser.parse_args()
    
    # Set up environment
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Add project root to Python path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    print(f"🚀 Starting Burr Agent Web Chat...")
    print(f"📍 Host: {args.host}")
    print(f"🔌 Port: {args.port}")
    print(f"🌐 URL: http://{args.host}:{args.port}")
    print(f"📁 Working directory: {project_root}")
    
    # Import and run the web chat
    try:
        from web_chat import ui
        
        # Configure NiceGUI
        ui.run(
            title='Burr Agent Web Chat',
            port=args.port,
            host=args.host,
            show=not args.debug,  # Don't auto-open browser in debug mode
            reload=args.reload,
            favicon='🤖',
            dark=False
        )
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting web chat: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
