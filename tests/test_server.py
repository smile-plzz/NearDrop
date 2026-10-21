import hashlib, http.client, json, os, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from server import Server, State, safe_name

class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=State(self.tmp.name);self.server=Server(('127.0.0.1',0),self.s)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.cookie=''
        _,_,headers=self.call('/api/bootstrap',{'token':self.s.bootstrap});self.cookie=headers['Set-Cookie'].split(';')[0]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.s.db.close();self.tmp.cleanup()
    def call(self,path,data=None,cookie=None,headers=None,raw=False):
        c=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=10)
        h={'Cookie':self.cookie if cookie is None else cookie,'X-NearDrop':'1'};h.update(headers or {})
        body=data if raw else json.dumps(data).encode() if data is not None else None
        c.request('POST' if data is not None else 'GET',path,body,h);r=c.getresponse();content=r.read();rh=dict(r.getheaders());status=r.status;c.close()
        return status,json.loads(content) if rh.get('Content-Type')=='application/json' else content,rh
    def phone(self):
        _,invite,_=self.call('/api/invite',{});token=invite['url'].split('#pair=')[1]
        status,_,h=self.call('/api/pair',{'token':token,'name':'iPhone'},cookie='');self.assertEqual(status,200)
        return h['Set-Cookie'].split(';')[0],token
    def upload(self,name,data,cookie=None):
        status,start,_=self.call('/api/upload/start',{'name':name,'size':len(data)},cookie);self.assertEqual(status,200)
        ident=start['id']
        if data:self.assertEqual(self.call('/api/upload/chunk?id='+ident+'&offset=0',data,cookie,raw=True)[0],200)
        self.assertEqual(self.call('/api/upload/finish',{'id':ident},cookie)[0],200);return ident
    def test_pairing_one_use_qr_and_owner_permissions(self):
        _,invite,_=self.call('/api/invite',{});self.assertEqual(self.call(invite['qr'])[0],200)
        phone,token=self.phone();self.assertEqual(self.call('/api/pair',{'token':token},cookie='')[0],410)
        self.assertEqual(self.call('/api/invite',{},phone)[0],403)
        self.assertEqual(self.call('/api/state',cookie='')[0],401)
        self.assertEqual(self.call('/api/stop',{},phone)[0],403)
    def test_bidirectional_bytes_and_ranges(self):
        phone,_=self.phone();data=os.urandom(900000);ident=self.upload('Holiday ♥.bin',data,phone)
        status,actual,_=self.call('/download/'+ident);self.assertEqual((status,actual),(200,data))
        status,part,h=self.call('/download/'+ident,cookie=phone,headers={'Range':'bytes=101-999'});self.assertEqual(status,206);self.assertEqual(part,data[101:1000])
        _,st,_=self.call('/api/state');self.assertEqual(st['files'][0]['sha256'],hashlib.sha256(data).hexdigest())
        ident=self.upload('from-laptop.txt',b'hello');self.assertEqual(self.call('/download/'+ident,cookie=phone)[1],b'hello')
    def test_resume_idempotent_finish_and_wrong_owner(self):
        phone,_=self.phone();_,r,_=self.call('/api/upload/start',{'name':'big.txt','size':6});ident=r['id']
        self.call('/api/upload/chunk?id='+ident+'&offset=0',b'abc',raw=True)
        self.assertEqual(self.call('/api/upload/finish',{'id':ident})[0],409)
        _,res,_=self.call('/api/upload/start',{'name':'big.txt','size':6,'id':ident});self.assertEqual(res['offset'],3)
        self.assertEqual(self.call('/api/upload/chunk?id='+ident+'&offset=0',b'abc',raw=True)[0],409)
        self.assertEqual(self.call('/api/upload/chunk?id='+ident+'&offset=3',b'def',phone,raw=True)[0],404)
        self.call('/api/upload/chunk?id='+ident+'&offset=3',b'def',raw=True)
        for _ in range(2):self.assertEqual(self.call('/api/upload/finish',{'id':ident})[0],200)
        self.assertEqual(self.call('/download/'+ident)[1],b'abcdef')
    def test_security_guards_and_traversal(self):
        self.assertEqual(self.call('/api/state',headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.call('/api/note',{'text':'bad'},headers={'Origin':'http://evil.test'})[0],403)
        self.assertEqual(self.call('/api/note',{'text':'bad'},headers={'X-NearDrop':''})[0],403)
        self.assertEqual(self.call('/../../server.py')[0],404)
        ident=self.upload('../../CON.txt',b'x');_,st,_=self.call('/api/state');self.assertNotIn('/',st['files'][0]['name']);self.assertEqual(len(list(self.s.files.iterdir())),1)
        self.assertEqual(safe_name('CON.txt'),'_CON.txt')
    def test_notes_deletion_revocation(self):
        phone,_=self.phone();self.call('/api/note',{'text':'<script>alert(1)</script>'},phone)
        _,st,_=self.call('/api/state');self.assertEqual(st['notes'][0]['text'],'<script>alert(1)</script>')
        ident=st['notes'][0]['id'];self.assertEqual(self.call('/api/delete',{'kind':'note','id':ident},phone)[0],403)
        self.call('/api/delete',{'kind':'note','id':ident});self.assertEqual(self.call('/api/state')[1]['notes'],[])
        dev=next(x for x in st['devices'] if not x['host']);self.call('/api/revoke',{'id':dev['id']});self.assertEqual(self.call('/api/state',cookie=phone)[0],401)
    def test_zero_duplicate_cancel_and_limits(self):
        a=self.upload('empty.txt',b'');b=self.upload('empty.txt',b'');self.assertNotEqual(a,b);self.assertEqual(self.call('/download/'+a)[1],b'')
        self.assertEqual(self.call('/api/upload/start',{'name':'x','size':-1})[0],413)
        self.assertEqual(self.call('/api/upload/start',{'name':'x','size':21*1024**3})[0],413)
        _,r,_=self.call('/api/upload/start',{'name':'x','size':3});self.call('/api/upload/cancel',{'id':r['id']});self.assertFalse((self.s.partial/r['id']).exists())
        self.call('/api/delete',{'kind':'file','id':a});self.assertEqual(self.call('/download/'+a)[0],404)
    def test_persistence_and_expiry(self):
        ident=self.upload('keep.txt',b'persist');self.call('/api/note',{'text':'remember'})
        another=State(self.tmp.name);self.assertEqual(another.db.execute('SELECT count(*) FROM files WHERE complete=1').fetchone()[0],1);self.assertEqual(another.db.execute('SELECT count(*) FROM notes').fetchone()[0],1);another.db.close()
        _,invite,_=self.call('/api/invite',{});token=invite['url'].split('#pair=')[1];self.s.invites[token]['expires']=0
        self.assertEqual(self.call('/api/pair',{'token':token},cookie='')[0],410)
        key=self.cookie.split('=',1)[1];self.s.sessions[key]['expires']=0;self.assertEqual(self.call('/api/state')[0],401)
if __name__=='__main__':unittest.main(verbosity=2)
