import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiClient} from '../src/api.js';
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
const session=(token='anon')=>({authenticated:false,username:null,csrf_token:token});

test('all API calls use the configured backend origin and include cookies',async()=>{
  const calls=[];
  const client=createApiClient({baseUrl:'http://127.0.0.1:8001/',fetchImpl:async(...args)=>{calls.push(args);return json({waiting:[]})}});
  await client.request('/api/staff/queue');
  assert.equal(calls[0][0],'http://127.0.0.1:8001/api/staff/queue');
  assert.equal(calls[0][1].credentials,'include');
});

test('login bootstraps CSRF and later writes use the rotated token',async()=>{
  const calls=[];
  const client=createApiClient({fetchImpl:async(url,options)=>{
    calls.push({url,options});
    if(url.endsWith('/session'))return json(session());
    if(url.endsWith('/login'))return json({...session('staff'),authenticated:true,username:'host'});
    return json({party:{id:'one'}});
  }});
  await client.login('host','test-only');
  await client.mutate('/api/staff/parties',{name:'Alex',size:2});
  assert.equal(calls[1].options.headers['X-CSRF-Token'],'anon');
  assert.equal(calls[2].options.headers['X-CSRF-Token'],'staff');
  assert.ok(calls[2].options.headers['Idempotency-Key']);
});

test('ambiguous mutation failure retains its request key for retry',async()=>{
  const keys=[];let fail=true;
  const client=createApiClient({fetchImpl:async(url,options)=>{
    if(url.endsWith('/session'))return json(session());
    keys.push(options.headers['Idempotency-Key']);
    if(fail){fail=false;throw new TypeError('connection lost')}
    return json({status_url:'/status/example'});
  }});
  const body={name:'Alex',size:2};
  await assert.rejects(client.mutate('/api/join',body),/Cannot reach/);
  await client.mutate('/api/join',body);
  assert.equal(keys[0],keys[1]);
});

test('a stale CSRF token refreshes once and preserves the idempotency key',async()=>{
  let bootstraps=0;const keys=[];const tokens=[];
  const client=createApiClient({fetchImpl:async(url,options)=>{
    if(url.endsWith('/session'))return json(session('csrf-'+(++bootstraps)));
    keys.push(options.headers['Idempotency-Key']);tokens.push(options.headers['X-CSRF-Token']);
    if(keys.length===1)return json({error:{code:'csrf_rejected',message:'stale'}},403);
    return json({ok:true});
  }});
  await client.mutate('/api/join',{name:'A',size:2});
  assert.deepEqual(tokens,['csrf-1','csrf-2']);assert.equal(keys[0],keys[1]);
});

test('wrong login errors stay on login but expired staff requests signal sign-in',async()=>{
  let redirects=0;
  const client=createApiClient({onUnauthorized:()=>redirects++,fetchImpl:async(url)=>{
    if(url.endsWith('/session'))return json(session());
    return json({error:{code:'invalid_credentials',message:'Incorrect password'}},401);
  }});
  await assert.rejects(client.login('host','wrong'),/Incorrect password/);
  assert.equal(redirects,0);
  await assert.rejects(client.request('/api/staff/queue'));
  assert.equal(redirects,1);
});

test('simultaneous public writes share the session bootstrap',async()=>{
  let count=0;
  const client=createApiClient({fetchImpl:async(url)=>{
    if(url.endsWith('/session')){count++;await new Promise(r=>setTimeout(r,10));return json(session())}
    return json({ok:true});
  }});
  await Promise.all([client.mutate('/api/join',{name:'A',size:2}),client.mutate('/api/join',{name:'B',size:2})]);
  assert.equal(count,1);
});

test('timeouts return a retryable error',async()=>{
  const client=createApiClient({timeoutMs:5,fetchImpl:async(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted'))))});
  await assert.rejects(client.request('/api/public-settings'),/timed out/);
});
