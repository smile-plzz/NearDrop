const { chromium }=require('playwright');
const {spawn}=require('child_process');
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert');
(async()=>{
const data=fs.mkdtempSync(path.join(os.tmpdir(),'neardrop-e2e-'));
const proc=spawn(process.env.PYTHON||'python3',['-u','app/server.py','--port','47829','--no-browser','--data-dir',data],{cwd:path.resolve(__dirname,'..')});
let browser;
try{
 const url=await new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('Startup timeout')),15000);proc.stdout.on('data',d=>{output+=d;const match=output.match(/http:\/\/127\.0\.0\.1:47829\/#host=\S+/);if(match){clearTimeout(timeout);resolve(match[0]);}});proc.on('exit',c=>reject(new Error('Server exited '+c)));});
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 const desktop=await browser.newContext({viewport:{width:1440,height:1100}}),phone=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'});
 const pc=await desktop.newPage(),mobile=await phone.newPage();const errors=[];for(const p of [pc,mobile])p.on('pageerror',e=>errors.push(e.message));
 await pc.goto(url);await pc.locator('#dashboard').waitFor({state:'visible'});
 await pc.locator('#pairDevice').click();await pc.locator('#pairDialog[open]').waitFor();
 const invite=await pc.locator('#inviteUrl').inputValue();assert(invite.includes('#pair='));
 await mobile.goto(invite.replace(/http:\/\/[^/]+/,'http://127.0.0.1:47829'));
 await mobile.locator('#deviceName').fill('Ismail’s iPhone');await mobile.locator('#connect').click();await mobile.locator('#dashboard').waitFor({state:'visible'});
 await pc.locator('#closeDialog').click();
 let interrupted=false;await mobile.route('**/api/upload/chunk?*',async route=>{if(!interrupted&&route.request().url().includes('offset=1048576')){interrupted=true;await route.abort('connectionreset');}else await route.continue();});
 const buffer=Buffer.alloc(2500000);for(let i=0;i<buffer.length;i++)buffer[i]=i%251;
 await mobile.locator('#fileInput').setInputFiles([{name:'Trip-original.bin',mimeType:'application/octet-stream',buffer},{name:'Notes.txt',mimeType:'text/plain',buffer:Buffer.from('Weekend plans')}]);
 await mobile.getByText('Saved on laptop · Ready to download').first().waitFor();
 await pc.getByText('Trip-original.bin',{exact:true}).waitFor();
 const down=pc.waitForEvent('download');await pc.getByRole('link',{name:'Download Trip-original.bin'}).click();const download=await down;assert.deepEqual(fs.readFileSync(await download.path()),buffer);
 await pc.locator('#fileInput').setInputFiles({name:'From-laptop.txt',mimeType:'text/plain',buffer:Buffer.from('Hello from laptop')});
 await mobile.getByText('From-laptop.txt',{exact:true}).waitFor();const d2=mobile.waitForEvent('download');await mobile.getByRole('link',{name:'Download From-laptop.txt'}).click();assert.equal(fs.readFileSync(await (await d2).path(),'utf8'),'Hello from laptop');
 await mobile.locator('#noteText').fill('https://example.com/trip');await mobile.locator('#sendNote').click();await pc.getByRole('link',{name:'Open link ↗'}).waitFor();
 await pc.locator('#noteText').fill('<img src=x onerror=alert(1)>');await pc.locator('#sendNote').click();await mobile.getByText('<img src=x onerror=alert(1)>',{exact:true}).waitFor();assert.equal(await mobile.locator('.note img').count(),0);
 assert(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
 await pc.locator('#search').fill('From-laptop');assert.equal(await pc.locator('.file-row').count(),1);await pc.locator('#search').fill('');
 fs.mkdirSync(path.resolve(__dirname,'../test-output'),{recursive:true});
 await pc.screenshot({path:path.resolve(__dirname,'../test-output/desktop.png'),fullPage:true});await mobile.screenshot({path:path.resolve(__dirname,'../test-output/mobile.png'),fullPage:true});
 await pc.locator('#devices').getByRole('button',{name:'Disconnect',exact:true}).click();await mobile.locator('#pair').waitFor({state:'visible',timeout:10000});
 assert(interrupted,'Network interruption was exercised');assert.deepEqual(errors,[]);console.log('PASS: desktop + mobile pairing, 2.5 MB upload with forced interruption and resume, multi-file queue, byte comparison, reverse download, notes, XSS rendering, search, responsive layout, revocation; no JS errors.');
}catch(e){console.error(e);process.exitCode=1;}finally{if(browser)await browser.close();proc.kill('SIGINT');await new Promise(r=>proc.on('exit',r));fs.rmSync(data,{recursive:true,force:true});}
})();
