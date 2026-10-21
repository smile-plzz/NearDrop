"""Exercise the extracted Windows distribution with its bundled runtime."""
import http.client, json, subprocess, sys, tempfile, time, zipfile
from pathlib import Path
archive=next(Path('dist').glob('*.zip'))
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(archive) as z:z.extractall(tmp)
    root=next(Path(tmp).glob('NearDrop-*'))
    runtime=root/'runtime/python.exe'
    subprocess.run([str(runtime),'-m','unittest','discover','-s','tests','-v'],cwd=root,check=True)
    proc=subprocess.Popen([str(runtime),'-u','app/server.py','--no-browser','--port','47833','--data-dir',str(Path(tmp)/'data')],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        import concurrent.futures
        def read_bootstrap():
            for line in proc.stdout:
                if 'Laptop dashboard:' in line:return line.strip().split('#host=',1)[1]
            raise RuntimeError('Server exited before dashboard was available.')
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(read_bootstrap)
            try: token=future.result(timeout=20)
            except Exception:proc.terminate();raise
        conn=http.client.HTTPConnection('127.0.0.1',47833,timeout=10)
        conn.request('POST','/api/bootstrap',json.dumps({'token':token}),{'Content-Type':'application/json','X-NearDrop':'1'})
        response=conn.getresponse();assert response.status==200,response.read();cookie=response.getheader('Set-Cookie').split(';')[0];response.read();conn.close()
        conn=http.client.HTTPConnection('127.0.0.1',47833,timeout=10)
        conn.request('GET','/api/state',headers={'Cookie':cookie});response=conn.getresponse();state=json.loads(response.read());assert response.status==200 and state['host']
        conn.close();print('PASS: extracted portable runtime starts, authenticates owner, and serves dashboard state on Windows.')
    finally:proc.terminate();proc.wait(timeout=10)
