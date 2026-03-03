#!/usr/bin/env python3
"""
BTC Trading Dashboard - Web Application Entry Point
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import create_app
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG

if __name__ == '__main__':
    print("=" * 70)
    print("  BTC 5-MIN TRADING DASHBOARD")
    print("=" * 70)
    print(f"\n  Starting web server...")
    print(f"  URL: http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"  Debug mode: {FLASK_DEBUG}")
    print("\n  Press Ctrl+C to stop\n")
    print("=" * 70)

    app, socketio = create_app()
    socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, allow_unsafe_werkzeug=True)
