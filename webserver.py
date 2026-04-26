import socket
import threading
import os
import time
from datetime import datetime
from email.utils import formatdate
import mimetypes

# Configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8080  # Use non-standard port to avoid conflict with port 80
SERVER_ROOT = './www'  # Directory where web files are stored
LOG_FILE = 'server.log'

# Response status codes and messages
STATUS_CODES = {
    200: '200 OK',
    400: '400 Bad Request',
    403: '403 Forbidden',
    404: '404 Not Found',
    304: '304 Not Modified'
}

# Global lock for thread-safe log writing
log_lock = threading.Lock()


def write_log(client_addr, requested_file, status_code):
    """Write a log entry to the log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{client_addr} | {timestamp} | {requested_file} | {status_code}\n"

    with log_lock:
        with open(LOG_FILE, 'a') as f:
            f.write(log_entry)

    print(f"[LOG] {log_entry.strip()}")


def get_mime_type(filepath):
    """Return the MIME type based on file extension."""
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type is None:
        if filepath.endswith('.html') or filepath.endswith('.htm'):
            return 'text/html'
        elif filepath.endswith('.css'):
            return 'text/css'
        elif filepath.endswith('.js'):
            return 'application/javascript'
        elif filepath.endswith('.jpg') or filepath.endswith('.jpeg'):
            return 'image/jpeg'
        elif filepath.endswith('.png'):
            return 'image/png'
        elif filepath.endswith('.gif'):
            return 'image/gif'
        elif filepath.endswith('.txt'):
            return 'text/plain'
        else:
            return 'application/octet-stream'
    return mime_type


def get_last_modified(filepath):
    """Get last modified time of a file in HTTP date format."""
    try:
        mod_time = os.path.getmtime(filepath)
        return formatdate(mod_time, usegmt=True)
    except:
        return None


def build_response(status_code, headers=None, body=b''):
    """Build an HTTP response."""
    status_line = f"HTTP/1.1 {STATUS_CODES[status_code]}\r\n"
    response = status_line.encode()
    if headers:
        for key, value in headers.items():
            response += f"{key}: {value}\r\n".encode()
    response += b"\r\n"
    response += body
    return response


def handle_client(client_socket, client_address):
    """
    Handle a single HTTP request from a client.
    Supports GET and HEAD methods.
    Handles: keep-alive, if-modified-since, various status codes.
    """
    try:
        # Set socket timeout to avoid hanging
        client_socket.settimeout(10)

        # Receive request data
        request_data = b''
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            request_data += chunk
            if b'\r\n\r\n' in request_data:
                # Check if this is a GET request with body (unlikely, but safe)
                content_length = 0
                headers_part = request_data.split(b'\r\n\r\n')[0]
                for line in headers_part.split(b'\r\n'):
                    if line.lower().startswith(b'content-length:'):
                        content_length = int(line.split(b':')[1].strip())
                # If we have headers + full body, break
                if len(request_data) >= len(headers_part) + 4 + content_length:
                    break

        if not request_data:
            return

        # Parse request line
        request_str = request_data.decode('utf-8', errors='ignore')
        lines = request_str.split('\r\n')
        if not lines:
            return

        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 2:
            # Bad request
            response = build_response(400)
            client_socket.send(response)
            write_log(client_address[0], 'INVALID_REQUEST', 400)
            return

        method, path = parts[0], parts[1]

        # Parse headers
        headers = {}
        for line in lines[1:]:
            if ': ' in line:
                key, value = line.split(': ', 1)
                headers[key.lower()] = value

        # Get connection type
        connection_header = headers.get('connection', '')
        keep_alive = connection_header.lower() == 'keep-alive'

        # Handle different methods
        if method == 'GET':
            serve_file(client_socket, client_address, path, headers, method='GET')
        elif method == 'HEAD':
            serve_file(client_socket, client_address, path, headers, method='HEAD')
        else:
            # Method not allowed (simplified to 400)
            response = build_response(400)
            client_socket.send(response)
            write_log(client_address[0], path, 400)

    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        if not keep_alive:
            client_socket.close()
        else:
            # For keep-alive, we still close after this request for simplicity
            # A full implementation would loop and reuse the connection
            client_socket.close()


def serve_file(client_socket, client_address, path, request_headers, method='GET'):
    """
    Serve a file for GET or HEAD requests.
    Handles security, not found, forbidden, if-modified-since.
    """
    # Security: prevent directory traversal
    safe_path = os.path.normpath(path.lstrip('/'))
    if safe_path.startswith('..') or safe_path.startswith('/'):
        response = build_response(403)
        client_socket.send(response)
        write_log(client_address[0], path, 403)
        return

    # If path is empty or ends with '/', serve index.html
    if not safe_path or safe_path.endswith('/'):
        safe_path = os.path.join(safe_path, 'index.html')

    full_path = os.path.join(SERVER_ROOT, safe_path)

    # Check if file exists
    if not os.path.exists(full_path):
        response = build_response(404)
        client_socket.send(response)
        write_log(client_address[0], path, 404)
        return

    # Check if it's a regular file
    if not os.path.isfile(full_path):
        response = build_response(403)
        client_socket.send(response)
        write_log(client_address[0], path, 403)
        return

    # Get file information
    last_modified = get_last_modified(full_path)
    content_type = get_mime_type(full_path)
    content_length = os.path.getsize(full_path)

    # Check If-Modified-Since header
    if_modified_since = request_headers.get('if-modified-since', '')
    if if_modified_since and last_modified:
        # Simple comparison - for production, use proper date parsing
        if if_modified_since == last_modified:
            response = build_response(304)
            client_socket.send(response)
            write_log(client_address[0], path, 304)
            return

    # Prepare headers
    response_headers = {
        'Content-Type': content_type,
        'Content-Length': str(content_length),
        'Last-Modified': last_modified,
        'Connection': 'close'  # Simplified: close after each request
    }

    # Read file content if GET request
    if method == 'GET':
        try:
            with open(full_path, 'rb') as f:
                file_content = f.read()
            response = build_response(200, response_headers, file_content)
        except Exception:
            response = build_response(403)
            write_log(client_address[0], path, 403)
            client_socket.send(response)
            return
    else:  # HEAD request
        response = build_response(200, response_headers)

    client_socket.send(response)
    write_log(client_address[0], path, 200)


def start_server():
    """Start the multi-threaded web server."""
    # Create server root directory if it doesn't exist
    if not os.path.exists(SERVER_ROOT):
        os.makedirs(SERVER_ROOT)
        # Create a sample index.html file
        with open(os.path.join(SERVER_ROOT, 'index.html'), 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head><title>Comp 2322 Web Server</title></head>
<body>
<h1>Welcome to the Multi-Thread Web Server!</h1>
<p>If you see this, your server is working correctly.</p>
</body>
</html>""")

    # Create socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen(10)

    print(f"Server started on http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Serving files from: {os.path.abspath(SERVER_ROOT)}")
    print(f"Log file: {LOG_FILE}")
    print("Press Ctrl+C to stop the server\n")

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"New connection from {client_address}")

            # Create a new thread for each client
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True
            client_thread.start()

    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server_socket.close()


if __name__ == '__main__':
    start_server()

