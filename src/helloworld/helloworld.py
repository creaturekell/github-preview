"""Simple HTTP server for preview environments."""
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class HelloWorldHandler(BaseHTTPRequestHandler):
    """HTTP request handler that returns Hello World."""
    
    def do_GET(self):
        """Handle GET requests."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # Get PR info from environment if available
        pr_number = os.getenv('PR_NUMBER', 'N/A')
        commit_sha = os.getenv('COMMIT_SHA', 'N/A')
        
        message = f"""
        <html>
        <head><title>Hello World - Preview</title></head>
        <body>
            <h1>Hello, World!</h1>
            <p>This is a preview environment.</p>
            <ul>
                <li>PR Number: {pr_number}</li>
                <li>Commit SHA: {commit_sha[:8] if commit_sha != 'N/A' else 'N/A'}</li>
            </ul>
        </body>
        </html>
        """
        self.wfile.write(message.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr."""
        pass

def main():
    """Start the HTTP server."""
    port = int(os.getenv('PORT', '8080'))
    server_address = ('', port)
    httpd = HTTPServer(server_address, HelloWorldHandler)
    print(f"Server running on port {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
