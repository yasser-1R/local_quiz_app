"""Kill the quiz server running on port 8000."""
import os
import signal
import subprocess

def kill_server():
    print("Stopping quiz server...")

    # Try Windows (PowerShell)
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | '
                 'ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }'],
                capture_output=True, text=True
            )
            print("Server stopped (Windows).")
            return
        except Exception as e:
            print(f"Windows method failed: {e}")

    # Try Unix/Linux/Mac
    try:
        result = subprocess.run(['lsof', '-ti', ':8000'], capture_output=True, text=True)
        pids = result.stdout.strip().split('\n')
        for pid in pids:
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"Killed process {pid}")
                except Exception as e:
                    print(f"Failed to kill {pid}: {e}")
        print("Server stopped.")
        return
    except Exception as e:
        print(f"Unix method failed: {e}")

    print("Could not stop server automatically.")
    print("Try: Ctrl+C in the terminal running the server")

if __name__ == "__main__":
    kill_server()
