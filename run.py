"""
Local Classroom Quiz - Launcher
Run this file to start the server on your teacher PC.
Students then open their browser and go to http://<teacher-ip>:8000
"""
import socket
import uvicorn
from app.main import app
from app.config import HOST, PORT


def get_local_ip() -> str:
    """Find the LAN IP of this machine (the one students will use)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't actually connect, just lets the OS pick the best interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    ip = get_local_ip()
    print("=" * 60)
    print("  LOCAL CLASSROOM QUIZ - starting server")
    print("=" * 60)
    print(f"  Teacher (this PC):   http://localhost:{PORT}/teacher")
    print(f"  Students connect to: http://{ip}:{PORT}")
    print(f"  Projector / Display: http://localhost:{PORT}/display")
    print("=" * 60)
    print("  Press CTRL+C to stop the server.")
    print("=" * 60)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
