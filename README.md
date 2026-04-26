# Multi-thread-Web-Server-

## Student Information
- **Name**: Lin Mei Ting
- **Student ID**: 24083891d
- **Course**: Comp 2322 Computer Networking

## Project Overview
This project implements a multi-threaded web server from scratch using Python socket programming. The server can handle multiple concurrent HTTP requests, supports GET and HEAD methods, implements various HTTP response status codes, and handles important HTTP headers including Connection, Last-Modified, and If-Modified-Since.

## Features Implemented
- ✅ Multi-threaded architecture (each client request handled in separate thread)
- ✅ Proper HTTP request/response message exchange
- ✅ GET command support for text files and image files
- ✅ HEAD command support
- ✅ Five response status codes: 200 OK, 400 Bad Request, 403 Forbidden, 404 Not Found, 304 Not Modified
- ✅ Last-Modified and If-Modified-Since header handling
- ✅ Connection header support (keep-alive and close)
- ✅ Request logging to file
- ✅ Error handling for common scenarios


### Python Version
- Python 3.7 or higher

### Required Libraries
No external libraries required - uses only Python standard libraries:
- socket
- threading
- os
- sys
- time
- datetime
- logging
- pathlib
- email.utils

## Installation

1. Clone the repository:
```bash
git clone []
cd web-server-project
