import socket
import threading
import os
import time
import datetime
from urllib.parse import unquote

# Configuration
HOST = '127.0.0.1'
PORT = 8080               
DOCUMENT_ROOT = './www'   
LOG_FILE = 'server.log'

# Ensure document root exists
os.makedirs(DOCUMENT_ROOT, exist_ok=True)

# Lock for writing log file
log_lock = threading.Lock()

def log_request(client_ip, resource, status_code, size=None, method='GET'):
    """Append one line to the log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_lock:
        with open(LOG_FILE, 'a') as f:
            line = f"{timestamp} | {client_ip} | {method} {resource} | {status_code}"
            if size is not None:
                line += f" | size={size}"
            f.write(line + '\n')

def get_mime_type(filepath):
    """Return a simple MIME type based on extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.html' or ext == '.htm':
        return 'text/html'
    elif ext == '.txt':
        return 'text/plain'
    elif ext == '.jpg' or ext == '.jpeg':
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.gif':
        return 'image/gif'
    else:
        return 'application/octet-stream'

def get_last_modified(filepath):
    """Return Last-Modified time string in HTTP format."""
    mtime = os.path.getmtime(filepath)
    return time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(mtime))

def handle_client(conn, addr):
    """Handle a single HTTP request (may be persistent)."""
    client_ip = addr[0]
    try:
        # Set timeout for this connection
        conn.settimeout(5.0)
        while True:
            # Receive request
            request_data = b''
            while b'\r\n\r\n' not in request_data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                if len(request_data) > 8192:   
                    break
            if not request_data:
                break

            # Parse request line
            try:
                request_text = request_data.decode('utf-8', errors='replace')
                lines = request_text.split('\r\n')
                if not lines:
                    break
                method, path, version = lines[0].split()
            except ValueError:
                # 400 Bad Request
                response = b'HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n'
                conn.sendall(response)
                log_request(client_ip, '-', '400 Bad Request')
                break

            # Normalize path
            path = unquote(path.split('?')[0])   
            if path == '/':
                path = '/index.html'
            # Security: prevent directory traversal
            safe_path = os.path.normpath(DOCUMENT_ROOT + path)
            if not safe_path.startswith(os.path.abspath(DOCUMENT_ROOT)):
                # 403 Forbidden
                response = b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'
                conn.sendall(response)
                log_request(client_ip, path, '403 Forbidden')
                break

            filepath = safe_path
            # Check Connection header
            connection_header = 'close'
            for line in lines[1:]:
                if line.lower().startswith('connection:'):
                    connection_header = line.split(':', 1)[1].strip().lower()
                    break

            # Handle If-Modified-Since
            if_modified_since = None
            for line in lines[1:]:
                if line.lower().startswith('if-modified-since:'):
                    if_modified_since = line.split(':', 1)[1].strip()
                    break

            # File existence and permissions
            if not os.path.exists(filepath):
                # 404 Not Found
                response_body = b'<html><body><h1>404 Not Found</h1></body></html>'
                response = b'HTTP/1.1 404 Not Found\r\n'
                response += b'Content-Type: text/html\r\n'
                response += b'Connection: close\r\n'
                response += b'Content-Length: ' + str(len(response_body)).encode() + b'\r\n\r\n'
                response += response_body
                conn.sendall(response)
                log_request(client_ip, path, '404 Not Found', len(response_body), method)
                break

            if not os.access(filepath, os.R_OK):
                # 403 Forbidden
                response_body = b'<html><body><h1>403 Forbidden</h1></body></html>'
                response = b'HTTP/1.1 403 Forbidden\r\n'
                response += b'Content-Type: text/html\r\n'
                response += b'Connection: close\r\n'
                response += b'Content-Length: ' + str(len(response_body)).encode() + b'\r\n\r\n'
                response += response_body
                conn.sendall(response)
                log_request(client_ip, path, '403 Forbidden', len(response_body), method)
                break

            # Check for 304 Not Modified
            last_modified = get_last_modified(filepath)
            if if_modified_since and if_modified_since == last_modified:
                response = b'HTTP/1.1 304 Not Modified\r\n'
                response += b'Connection: ' + connection_header.encode() + b'\r\n'
                response += b'Last-Modified: ' + last_modified.encode() + b'\r\n\r\n'
                conn.sendall(response)
                log_request(client_ip, path, '304 Not Modified', method=method)
                if connection_header == 'close':
                    break
                else:
                    continue   # persistent: wait for next request

            # Read file
            with open(filepath, 'rb') as f:
                file_content = f.read()
            content_type = get_mime_type(filepath)

            if method == 'HEAD':
                # HEAD
                response = b'HTTP/1.1 200 OK\r\n'
                response += b'Content-Type: ' + content_type.encode() + b'\r\n'
                response += b'Content-Length: ' + str(len(file_content)).encode() + b'\r\n'
                response += b'Last-Modified: ' + last_modified.encode() + b'\r\n'
                response += b'Connection: ' + connection_header.encode() + b'\r\n\r\n'
                conn.sendall(response)
                log_request(client_ip, path, '200 OK', len(file_content), 'HEAD')
            elif method == 'GET':
                response = b'HTTP/1.1 200 OK\r\n'
                response += b'Content-Type: ' + content_type.encode() + b'\r\n'
                response += b'Content-Length: ' + str(len(file_content)).encode() + b'\r\n'
                response += b'Last-Modified: ' + last_modified.encode() + b'\r\n'
                response += b'Connection: ' + connection_header.encode() + b'\r\n\r\n'
                response += file_content
                conn.sendall(response)
                log_request(client_ip, path, '200 OK', len(file_content), 'GET')
            else:
                # Method not allowed (we only implement GET/HEAD)
                response_body = b'<html><body><h1>400 Bad Request</h1></body></html>'
                response = b'HTTP/1.1 400 Bad Request\r\n'
                response += b'Connection: close\r\n\r\n'
                response += response_body
                conn.sendall(response)
                log_request(client_ip, path, '400 Bad Request', len(response_body), method)
                break

            # If non-persistent, close; else keep connection open for next request
            if connection_header == 'close':
                break

    except socket.timeout:
        pass
    except Exception as e:
        print(f"Error handling {addr}: {e}")
    finally:
        conn.close()

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    print(f"Web server running on {HOST}:{PORT}")
    print(f"Serving files from {os.path.abspath(DOCUMENT_ROOT)}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            conn, addr = server_socket.accept()
            # multi‑threaded
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server_socket.close()

if __name__ == '__main__':
    start_server()
