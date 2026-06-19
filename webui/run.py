#!/usr/bin/env python3
"""
Kronos Web UI startup script
"""

import os
import sys
import subprocess
import webbrowser
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def check_dependencies():
    """Check if dependencies are installed"""
    try:
        import flask
        import flask_cors
        import pandas
        import numpy
        import plotly
        print("✅ All dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def install_dependencies():
    """Install dependencies"""
    print("Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installation completed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Dependencies installation failed")
        return False

def main():
    """Main function"""
    print("🚀 Starting Kronos Web UI...")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\nAuto-install dependencies? (y/n): ", end="")
        if input().lower() == 'y':
            if not install_dependencies():
                return
        else:
            print("Please manually install dependencies and retry")
            return
    
    # Check model availability
    try:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from model import Kronos, KronosTokenizer, KronosPredictor
        print("✅ Kronos model library available")
        model_available = True
    except ImportError:
        print("⚠️  Kronos model library not available, will use simulated prediction")
        model_available = False
    
    # Start Flask application
    print("\n🌐 Starting Web server...")
    
    # Set environment variables
    os.environ['FLASK_APP'] = 'app.py'
    os.environ['FLASK_ENV'] = 'development'
    
    # Start server
    try:
        from app import app
        host = os.environ.get("KRONOS_WEBUI_HOST", "127.0.0.1")
        port = int(os.environ.get("KRONOS_WEBUI_PORT", os.environ.get("PORT", "7070")))
        open_browser = os.environ.get("KRONOS_WEBUI_OPEN_BROWSER", "1").lower() not in {"0", "false", "no", "off"}
        # Debug stays available, but the file-watch reloader is OFF by default:
        # webui/ holds runtime artifacts (rl_runs, stom_predictions, logs) that
        # change constantly, which would otherwise restart the server in a loop
        # and re-open the browser tab on every restart. Opt back in with
        # KRONOS_WEBUI_RELOAD=1 when editing server code.
        debug_mode = os.environ.get("KRONOS_WEBUI_DEBUG", "1").lower() not in {"0", "false", "no", "off"}
        use_reloader = os.environ.get("KRONOS_WEBUI_RELOAD", "0").lower() in {"1", "true", "yes", "on"}
        # In the reloader child process Werkzeug sets WERKZEUG_RUN_MAIN; never
        # re-open the browser there, otherwise each restart spawns a new tab.
        is_reloader_child = bool(os.environ.get("WERKZEUG_RUN_MAIN"))
        access_host = "localhost" if host in {"0.0.0.0", "::"} else host
        access_url = f"http://{access_host}:{port}"

        print("✅ Web server started successfully!")
        print(f"🌐 Access URL: {access_url}")
        print("💡 Tip: Press Ctrl+C to stop server")

        # Auto-open browser once, only in the main process and only if enabled.
        if open_browser and not is_reloader_child:
            time.sleep(2)
            webbrowser.open(access_url)

        # Start Flask application
        app.run(debug=debug_mode, host=host, port=port, use_reloader=use_reloader)
        
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        print("Please check if port 7070 is occupied")

if __name__ == "__main__":
    main()
