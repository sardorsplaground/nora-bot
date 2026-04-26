import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        key = os.environ.get('RESEND_API_KEY', '')
        nora_email = os.environ.get('NORA_EMAIL', 'nora@vitafirst.co')
        result = {'key_prefix': key[:12] + '...' if key else 'MISSING', 'from': nora_email}
        try:
            payload = json.dumps({
                'from': f'Nora <{nora_email}>',
                'to': ['sardor@bolderapps.com'],
                'subject': 'Nora Test',
                'text': 'Test email from Nora diagnostic endpoint.'
            }).encode('utf-8')
            req = Request('https://api.resend.com/emails', data=payload, headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {key}'
            })
            with urlopen(req, timeout=10) as r:
                body = r.read().decode()
                result['status'] = r.status
                result['response'] = json.loads(body)
        except Exception as e:
            result['error'] = str(e)
            if hasattr(e, 'read'):
                try:
                    result['error_body'] = e.read().decode()
                except:
                    pass
            if hasattr(e, 'code'):
                result['error_code'] = e.code
            if hasattr(e, 'headers'):
                result['error_headers'] = dict(e.headers)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
