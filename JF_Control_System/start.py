"""One-click launcher for JF_Control_System.
Starts backend (uvicorn on :8000) and frontend (Vite on :5173).
"""
import subprocess
import sys
import time
import webbrowser
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print("=== JF_Control_System Starting ===")

    backend = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "run.py")],
        cwd=ROOT,
    )
    print("[backend] Started uvicorn on :8000")

    frontend_dir = os.path.join(ROOT, "frontend")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
    )
    print("[frontend] Started Vite on :5173")

    time.sleep(3)
    webbrowser.open("http://localhost:5173")

    print("=== Ready ===")
    print("Backend:  http://localhost:8000")
    print("Frontend: http://localhost:5173")
    print("Press Ctrl+C to stop all.")

    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print("Stopped.")


if __name__ == "__main__":
    main()
