"""NearDrop: local, paired file and text sharing. Python 3.11+, no cloud."""
from __future__ import annotations
import argparse, hashlib, io, json, mimetypes, os, re, secrets, shutil, socket, sqlite3, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import segno
VERSION = '1.0.0'
CHUNK = 1024 * 1024
MAX_FILE = 20 * 1024**3

def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if not info[4][0].startswith('127.'): ips.add(info[4][0])
    except OSError: pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 9)); ips.add(s.getsockname()[0])
    except OSError: pass
    return sorted(ips) or ['127.0.0.1']

def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', str(name)).strip(' .')[:180]
    while len(name.encode('utf-8')) > 180: name = name[:-1]
    if not name: name = 'Untitled'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{x}{n}' for x in ['COM','LPT'] for n in range(1,10)]}: name = '_' + name
    return name

class State:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.files = self.root / 'Received'; self.files.mkdir(exist_ok=True)
        self.partial = self.root / 'Partial'; self.partial.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'neardrop.sqlite', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, name TEXT, size INTEGER, created REAL, device TEXT, owner TEXT, complete INTEGER DEFAULT 0, sha256 TEXT);
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, text TEXT, created REAL, device TEXT);
        ''')
        self.db.commit()
        self.sessions = {}; self.invites = {}; self.attempts = {}; self.bootstrap = secrets.token_urlsafe(32)
        self.ips = local_ips()
        # Incomplete files from a previous process cannot be authenticated for resumption.
        for row in self.db.execute('SELECT id FROM files WHERE complete=0').fetchall():
            (self.partial / row['id']).unlink(missing_ok=True)
        self.db.execute('DELETE FROM files WHERE complete=0'); self.db.commit()

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, address, state):
        self.state = state
        super().__init__(address, Handler)
        self.port = self.server_address[1]
        self.hosts = {f'{ip}:{self.port}' for ip in state.ips + ['127.0.0.1','localhost']}

class Problem(Exception):
    def __init__(self, status, message): self.status, self.message = status, message

class Handler(BaseHTTPRequestHandler):
    server_version = 'NearDrop'
    def log_message(self, *args): pass # Never log pairing tokens or file names.
    def setup(self):
        super().setup(); self.connection.settimeout(30)
    @property
    def s(self): return self.server.state
    def headers_out(self, status, kind='application/json', length=None, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if length is not None: self.send_header('Content-Length',str(length))
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers()
    def reply(self, data, status=200, extra=None):
        raw = json.dumps(data).encode(); self.headers_out(status,length=len(raw),extra=extra); self.wfile.write(raw)
    def body(self, limit=65536):
        if self.headers.get('Transfer-Encoding'): raise Problem(400,'Chunked HTTP bodies are not supported.')
        try: n = int(self.headers.get('Content-Length','0'))
        except ValueError: raise Problem(400,'Invalid request length.')
        if not 0 <= n <= limit: raise Problem(413,'Request too large.')
        data = self.rfile.read(n)
        if len(data) != n: raise Problem(400,'Transfer interrupted. Retry to resume.')
        return data
    def js(self):
        try:
            value = json.loads(self.body())
            if not isinstance(value,dict): raise ValueError()
            return value
        except (ValueError, UnicodeError): raise Problem(400,'Invalid request.')
    def auth(self, owner=False):
        cookies = dict(x.strip().split('=',1) for x in self.headers.get('Cookie','').split(';') if '=' in x)
        token = cookies.get('nd','')
        session = self.s.sessions.get(token)
        if not session or session['expires'] < time.time(): raise Problem(401,'Pair this device to continue.')
        if owner and not session['host']: raise Problem(403,'Only the laptop can do that.')
        return token, session
    def guard(self, mutation=False):
        host = self.headers.get('Host','')
        if host not in self.server.hosts: raise Problem(403,'Unrecognized address. Open the address shown on your laptop.')
        if mutation:
            if self.headers.get('X-NearDrop') != '1': raise Problem(403,'Open NearDrop to perform this action.')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host: raise Problem(403,'Cross-site request blocked.')
    def dispatch(self, method):
        try:
            self.guard(method != 'GET')
            if method == 'GET': self.get()
            else:
                with self.s.lock: self.post()
        except Problem as e: self.reply({'error':e.message},e.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError): pass
        except (ValueError,TypeError,KeyError): self.reply({'error':'Invalid request values.'},400)
        except OSError as e:
            self.reply({'error':'Storage or connection unavailable. Check free disk space and try again.'},507)
        except Exception:
            self.reply({'error':'Unexpected error. Restart NearDrop if this continues.'},500)
    def do_GET(self): self.dispatch('GET')
    def do_POST(self): self.dispatch('POST')
    def get(self):
        u = urlsplit(self.path); path = u.path
        if path in ['/','/app.js','/style.css','/icon.svg']:
            file = Path(__file__).parent / {'/':'index.html','/app.js':'app.js','/style.css':'style.css','/icon.svg':'icon.svg'}[path]
            data = file.read_bytes(); self.headers_out(200,mimetypes.guess_type(file.name)[0] or 'text/plain',len(data)); self.wfile.write(data); return
        token, session = self.auth()
        if path == '/api/state':
            with self.s.lock:
                files = [dict(r) for r in self.s.db.execute('SELECT id,name,size,created,device,sha256 FROM files WHERE complete=1 ORDER BY created DESC LIMIT 500')]
                notes = [dict(r) for r in self.s.db.execute('SELECT * FROM notes ORDER BY created DESC LIMIT 100')]
                devices = [{'id':x['id'],'name':x['name'],'host':x['host']} for x in self.s.sessions.values() if x['expires'] > time.time()]
            self.reply({'version':VERSION,'host':session['host'],'device':session['name'],'files':files,'notes':notes,'devices':devices if session['host'] else [],'free':shutil.disk_usage(self.s.root).free,'addresses':[f'http://{ip}:{self.server.port}' for ip in self.s.ips],'folder':str(self.s.files) if session['host'] else None}); return
        if path == '/api/qr':
            self.auth(True); invite = parse_qs(u.query).get('invite',[''])[0]
            info = self.s.invites.get(invite)
            if not info or info['expires'] < time.time(): raise Problem(410,'Pairing link expired. Create a new one.')
            output = io.BytesIO(); segno.make(info['url']).save(output,kind='svg',scale=7,border=3)
            raw = output.getvalue(); self.headers_out(200,'image/svg+xml',len(raw)); self.wfile.write(raw); return
        if path.startswith('/download/'):
            file_id = path.split('/')[-1]
            with self.s.lock: row = self.s.db.execute('SELECT * FROM files WHERE id=? AND complete=1',(file_id,)).fetchone()
            if not row: raise Problem(404,'File is no longer available.')
            target = self.s.files / (row['id'] + '_' + row['name'])
            size = target.stat().st_size; start = 0; end = size-1; status=200
            if self.headers.get('Range'):
                match = re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
                if not match: raise Problem(416,'Unsupported download range.')
                start=int(match[1]); end=min(int(match[2]) if match[2] else end,end)
                if start > end or start >= size: raise Problem(416,'Invalid download range.')
                status=206
            extra={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['name']), 'Accept-Ranges':'bytes'}
            if status==206: extra['Content-Range']=f'bytes {start}-{end}/{size}'
            with target.open('rb') as f:
                self.headers_out(status,'application/octet-stream',end-start+1,extra)
                f.seek(start); remaining=end-start+1
                while remaining:
                    data=f.read(min(CHUNK,remaining))
                    if not data: break
                    self.wfile.write(data); remaining-=len(data)
            return
        raise Problem(404,'Not found.')
    def session(self, name, host):
        # Remove expired sessions before enforcing cap.
        self.s.sessions={k:v for k,v in self.s.sessions.items() if v['expires']>time.time()}
        if len(self.s.sessions)>=16: raise Problem(429,'Device limit reached. Disconnect a device on the laptop.')
        token=secrets.token_urlsafe(32)
        self.s.sessions[token]={'name':str(name).strip()[:60] or 'Phone','host':host,'expires':time.time()+86400,'id':secrets.token_hex(8)}
        self.reply({'ok':True},extra={'Set-Cookie':f'nd={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'})
    def post(self):
        path=urlsplit(self.path).path
        if path in ['/api/bootstrap','/api/pair']:
            ip=self.client_address[0]; now=time.time()
            attempts=[t for t in self.s.attempts.get(ip,[]) if now-t<60]
            if len(attempts)>=12: raise Problem(429,'Too many pairing attempts. Wait one minute.')
            self.s.attempts[ip]=attempts+[now]
            data=self.js()
            if path=='/api/bootstrap':
                if ip not in ['127.0.0.1','::1'] or not secrets.compare_digest(str(data.get('token','')),self.s.bootstrap): raise Problem(403,'Open the laptop window from the NearDrop launcher.')
                self.s.bootstrap=secrets.token_urlsafe(32); self.session('This laptop',True)
            else:
                invite=str(data.get('token','')); info=self.s.invites.get(invite)
                if not info or info['expires']<now: raise Problem(410,'Pairing link expired or already used. Create a new link on the laptop.')
                self.session(data.get('name','Phone'),False); self.s.invites.pop(invite,None)
            return
        token,session=self.auth()
        if path=='/api/upload/chunk':
            q=parse_qs(urlsplit(self.path).query); file_id=q.get('id',[''])[0]; offset=int(q.get('offset',['-1'])[0])
            row=self.s.db.execute('SELECT * FROM files WHERE id=? AND complete=0 AND owner=?',(file_id,token)).fetchone()
            if not row: raise Problem(404,'Upload expired. Start the file again.')
            target=self.s.partial/file_id
            if target.stat().st_size!=offset: raise Problem(409,'Upload offset changed. Retry to resume.')
            raw=self.body(CHUNK)
            if not raw or offset+len(raw)>row['size']: raise Problem(400,'Invalid chunk size.')
            with target.open('ab') as f: f.write(raw); f.flush()
            self.reply({'offset':offset+len(raw)}); return
        data=self.js()
        if path=='/api/invite':
            self.auth(True)
            address=data.get('address',f'http://{self.s.ips[0]}:{self.server.port}')
            if address not in [f'http://{ip}:{self.server.port}' for ip in self.s.ips]: raise Problem(400,'Choose a listed network address.')
            invite=secrets.token_urlsafe(24); url=address+'/#pair='+invite
            self.s.invites={invite:{'url':url,'expires':time.time()+300}}
            self.reply({'url':url,'expires':self.s.invites[invite]['expires'],'qr':'/api/qr?invite='+invite}); return
        if path=='/api/upload/start':
            name=safe_name(data.get('name','')); size=int(data.get('size',-1))
            if not 0<=size<=MAX_FILE: raise Problem(413,'Maximum file size is 20 GB.')
            file_id=data.get('id','')
            row=self.s.db.execute('SELECT * FROM files WHERE id=? AND owner=?',(file_id,token)).fetchone()
            if row:
                if row['size']!=size or row['name']!=name: raise Problem(409,'File does not match the previous upload.')
                self.reply({'id':row['id'],'offset':size if row['complete'] else (self.s.partial/row['id']).stat().st_size,'complete':bool(row['complete'])}); return
            reserved=sum(r['size']-(self.s.partial/r['id']).stat().st_size for r in self.s.db.execute('SELECT id,size FROM files WHERE complete=0'))
            if size+reserved+100*1024**2>shutil.disk_usage(self.s.root).free: raise Problem(507,'Not enough space on the laptop.')
            if self.s.db.execute('SELECT COUNT(*) FROM files WHERE complete=0').fetchone()[0]>=64: raise Problem(429,'Too many unfinished uploads. Cancel a transfer first.')
            file_id=secrets.token_hex(16); (self.s.partial/file_id).touch()
            self.s.db.execute('INSERT INTO files(id,name,size,created,device,owner) VALUES(?,?,?,?,?,?)',(file_id,name,size,time.time(),session['name'],token)); self.s.db.commit()
            self.reply({'id':file_id,'offset':0,'complete':False}); return
        if path=='/api/upload/finish':
            row=self.s.db.execute('SELECT * FROM files WHERE id=? AND owner=?',(data.get('id'),token)).fetchone()
            if not row: raise Problem(404,'Upload not found.')
            if row['complete']: self.reply({'ok':True,'sha256':row['sha256']}); return
            target=self.s.partial/row['id']
            if target.stat().st_size!=row['size']: raise Problem(409,'Upload is incomplete. Retry to resume.')
            with target.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
            target.replace(self.s.files/(row['id']+'_'+row['name']))
            self.s.db.execute('UPDATE files SET complete=1,sha256=? WHERE id=?',(digest,row['id'])); self.s.db.commit()
            self.reply({'ok':True,'sha256':digest}); return
        if path=='/api/upload/cancel':
            row=self.s.db.execute('SELECT id FROM files WHERE id=? AND complete=0 AND owner=?',(data.get('id'),token)).fetchone()
            if row:
                (self.s.partial/row['id']).unlink(missing_ok=True)
                self.s.db.execute('DELETE FROM files WHERE id=?',(row['id'],)); self.s.db.commit()
            self.reply({'ok':True}); return
        if path=='/api/note':
            content=str(data.get('text','')).strip()
            if not 0<len(content)<=16000: raise Problem(400,'Enter between 1 and 16,000 characters.')
            self.s.db.execute('INSERT INTO notes VALUES(?,?,?,?)',(secrets.token_hex(16),content,time.time(),session['name'])); self.s.db.commit(); self.reply({'ok':True}); return
        if path=='/api/logout':
            self.s.sessions.pop(token,None); self.reply({'ok':True},extra={'Set-Cookie':'nd=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'}); return
        self.auth(True)
        if path=='/api/delete':
            ident=data.get('id'); kind=data.get('kind')
            if kind=='file':
                row=self.s.db.execute('SELECT * FROM files WHERE id=? AND complete=1',(ident,)).fetchone()
                if row: (self.s.files/(row['id']+'_'+row['name'])).unlink(missing_ok=True)
                self.s.db.execute('DELETE FROM files WHERE id=? AND complete=1',(ident,))
            elif kind=='note': self.s.db.execute('DELETE FROM notes WHERE id=?',(ident,))
            else: raise Problem(400,'Invalid item type.')
            self.s.db.commit(); self.reply({'ok':True}); return
        if path=='/api/revoke':
            for key,val in list(self.s.sessions.items()):
                if val['id']==data.get('id') and not val['host']: self.s.sessions.pop(key)
            self.reply({'ok':True}); return
        if path=='/api/open-folder':
            if os.name=='nt': os.startfile(self.s.files)
            self.reply({'ok':True,'folder':str(self.s.files)}); return
        if path=='/api/stop':
            self.reply({'ok':True}); threading.Thread(target=self.server.shutdown,daemon=True).start(); return
        raise Problem(404,'Not found.')

def main():
    parser=argparse.ArgumentParser(description='NearDrop — phone to laptop, without the cloud')
    parser.add_argument('--port',type=int,default=47821); parser.add_argument('--data-dir',default=str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'NearDrop'))
    parser.add_argument('--no-browser',action='store_true'); args=parser.parse_args()
    root=Path(args.data_dir); root.mkdir(parents=True,exist_ok=True)
    lock_file=(root/'instance.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            if lock_file.seek(0,2)==0: lock_file.write(b'0'); lock_file.flush()
            lock_file.seek(0); msvcrt.locking(lock_file.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        print('NearDrop is already using this data folder. Close the other instance first.')
        lock_file.close(); return 1
    state=State(args.data_dir)
    try: server=Server(('0.0.0.0',args.port),state)
    except OSError:
        print('NearDrop could not start. Another copy may already be running. Close it or choose --port 47822.'); return 1
    url=f'http://127.0.0.1:{server.port}/#host={state.bootstrap}'
    print(f'NearDrop {VERSION}\nKeep this window open. Press Ctrl+C to stop.\nReceived files: {state.files}\nLaptop dashboard: {url}\nUse only on trusted Wi-Fi. Local HTTP is not encrypted.')
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); state.db.close(); lock_file.close()
    return 0
if __name__=='__main__': raise SystemExit(main())
