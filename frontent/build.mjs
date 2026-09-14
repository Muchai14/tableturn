import {cp,mkdir,writeFile} from 'node:fs/promises';
await mkdir('dist',{recursive:true});
await cp('public','dist',{recursive:true});
await cp('src','dist/src',{recursive:true});
const routes={'':'dashboard','staff':'dashboard','staff/login':'login','staff/summary':'summary','join':'join'};
for(const [route,page] of Object.entries(routes)){
  await mkdir(`dist/${route}`,{recursive:true});
  await cp(`public/pages/${page}.html`,`dist/${route?route+'/':''}index.html`);
}
// Static hosts must route /status/* to this guest template.
await cp('public/pages/guest.html','dist/guest.html');
await writeFile('dist/_redirects','/status/* /guest.html 200\n');
console.log('Built static frontend in dist/. Configure /status/* → /guest.html on your static host.');

if(process.env.TABLETURN_API_BASE_URL)await writeFile('dist/runtime-config.js','window.TABLETURN_CONFIG='+JSON.stringify({apiBaseUrl:process.env.TABLETURN_API_BASE_URL})+';');
