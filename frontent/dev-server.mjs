// Static development server only: no application API, database, or backend logic.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const routes={'/':'dashboard','/staff':'dashboard','/staff/login':'login','/staff/summary':'summary','/join':'join'};
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'};
http.createServer(async(req,res)=>{
  if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);return res.end('Static preview only');}
  try{
    const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(pathname==='/runtime-config.js' && process.env.TABLETURN_API_BASE_URL){
      res.writeHead(200,{'Content-Type':'text/javascript','Cache-Control':'no-store'});
      return res.end('window.TABLETURN_CONFIG='+JSON.stringify({apiBaseUrl:process.env.TABLETURN_API_BASE_URL})+';');
    }
    const page=routes[pathname]||(pathname.startsWith('/status/')?'guest':null);
    const relative=page?`public/pages/${page}.html`:pathname.startsWith('/src/')?pathname.slice(1):`public${pathname}`;
    const file=path.resolve(root,relative);
    if(!['public','src'].some(dir=>file.startsWith(path.join(root,dir)+path.sep)))throw new Error('Invalid path');
    const bytes=await readFile(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]||'text/plain','Cache-Control':'no-store','Referrer-Policy':'no-referrer'});
    res.end(req.method==='HEAD'?undefined:bytes);
  }catch{res.writeHead(404);res.end('Not found');}
}).listen(Number(process.env.PORT||5173),'127.0.0.1',()=>console.log('TableTurn frontend: http://127.0.0.1:'+ (process.env.PORT||5173)));
