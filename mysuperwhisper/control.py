"""
Local control socket for signaling a running MySuperWhisper instance.
"""

import os
import socket
import threading


class ControlServer:
    """Small Unix socket server for local control commands."""

    def __init__(self, socket_path, handlers, log):
        self.socket_path = str(socket_path)
        self.handlers = handlers
        self.log = log
        self._server = None
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError as exc:
                raise RuntimeError(f"Unable to remove stale control socket: {exc}") from exc

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.socket_path)
        self._server.listen(5)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self):
        self._stop_event.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

    def _serve(self):
        while not self._stop_event.is_set():
            try:
                conn, _ = self._server.accept()
            except OSError:
                break

            with conn:
                try:
                    payload = conn.recv(256).decode("utf-8").strip()
                    if not payload:
                        conn.sendall(b"ERROR empty command\n")
                        continue

                    handler = self.handlers.get(payload)
                    if handler is None:
                        conn.sendall(b"ERROR unknown command\n")
                        continue

                    handler()
                    conn.sendall(b"OK\n")
                except Exception as exc:
                    self.log(f"Control command failed: {payload}: {exc}", "error")
                    conn.sendall(f"ERROR {exc}\n".encode("utf-8"))


def send_command(socket_path, command, timeout=1.0):
    """Send a control command to the running instance."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(socket_path))
        sock.sendall(f"{command}\n".encode("utf-8"))
        reply = sock.recv(256).decode("utf-8").strip()
        return reply == "OK", reply or "No response"
    except FileNotFoundError:
        return False, "No running MySuperWhisper instance found."
    except ConnectionRefusedError:
        return False, "MySuperWhisper control socket exists but is not accepting connections."
    except OSError as exc:
        return False, f"Unable to contact MySuperWhisper: {exc}"
    finally:
        sock.close()
