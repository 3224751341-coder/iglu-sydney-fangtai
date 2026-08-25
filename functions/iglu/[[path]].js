const AGENT_CODE = 'A1336';
const IGLU_ORIGIN = 'https://iglu.com.au';

let cachedCookie = null;
let cookieExpiry = 0;

async function getSessionCookie() {
  if (cachedCookie && Date.now() < cookieExpiry) return cachedCookie;

  try {
    const resp = await fetch(`${IGLU_ORIGIN}/wp-admin/admin-ajax.php`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': IGLU_ORIGIN,
        'Referer': `${IGLU_ORIGIN}/iglu-agent-portal-login/`,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
      },
      body: `action=iglu_agent_login&agent_code=${AGENT_CODE}`,
    });

    const setCookies = resp.headers.getSetCookie?.() || [];
    const cookies = [];
    for (const sc of setCookies) {
      cookies.push(sc.split(';')[0]);
    }

    if (cookies.length > 0) {
      cachedCookie = cookies.join('; ');
      cookieExpiry = Date.now() + 5 * 60 * 1000;
      return cachedCookie;
    }
  } catch (e) {
    console.error('Agent login failed:', e.message);
  }
  return '';
}

export async function onRequest(context) {
  const { request, params } = context;
  const cookie = await getSessionCookie();

  const url = new URL(request.url);
  const targetPath = '/' + (params.path || []).join('/');
  const targetUrl = IGLU_ORIGIN + targetPath + url.search;

  const headers = new Headers();
  const accept = request.headers.get('Accept');
  if (accept) headers.set('Accept', accept);
  const acceptLang = request.headers.get('Accept-Language');
  if (acceptLang) headers.set('Accept-Language', acceptLang);
  const ct = request.headers.get('Content-Type');
  if (ct) headers.set('Content-Type', ct);
  headers.set('Cookie', cookie);
  headers.set('Referer', `${IGLU_ORIGIN}/iglu-agent-portal-login/`);
  headers.set('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36');

  const init = { method: request.method, headers };
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.text();
  }

  let resp;
  try {
    resp = await fetch(targetUrl, init);
  } catch (e) {
    return new Response('Proxy error: ' + e.message, { status: 502 });
  }

  // Handle redirects: rewrite Location to go through proxy
  if (resp.status >= 300 && resp.status < 400) {
    const loc = resp.headers.get('Location');
    if (loc) {
      let newLoc = loc;
      if (loc.startsWith(IGLU_ORIGIN)) {
        newLoc = '/iglu' + loc.substring(IGLU_ORIGIN.length);
      } else if (loc.startsWith('/') && !loc.startsWith('/iglu')) {
        newLoc = '/iglu' + loc;
      }
      return Response.redirect(new URL(newLoc, request.url).toString(), resp.status);
    }
  }

  const contentType = resp.headers.get('Content-Type') || '';

  if (contentType.includes('text/html')) {
    let html = await resp.text();
    const proxyOrigin = new URL('/iglu/', request.url).origin + '/iglu/';

    html = html.replace(/<head([^>]*)>/i, `<head$1><base href="${IGLU_ORIGIN}/">`);

    const interceptor = `<script>
(function(){
  var P='${proxyOrigin}';
  function rw(u){
    if(!u||typeof u!=='string')return u;
    if(u.indexOf(P)===0)return u;
    if(u.indexOf('iglu.com.au')>=0){try{var x=new URL(u);return P+x.pathname.substring(1)+x.search+x.hash;}catch(e){}}
    if(u[0]==='/'&&!u.startsWith('/iglu/'))return P+u.substring(1);
    return u;
  }
  var oo=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){return oo.call(this,m,rw(u));};
  var of=window.fetch;
  if(of)window.fetch=function(i,o){if(typeof i==='string')i=rw(i);else if(i instanceof Request)i=new Request(rw(i.url),i);return of.call(this,i,o);};
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('form').forEach(function(f){var a=f.getAttribute('action');if(a)f.setAttribute('action',rw(a));});
    document.querySelectorAll('a[href]').forEach(function(a){var h=a.getAttribute('href');if(h&&(h[0]==='/'||h.indexOf('iglu.com.au')>=0))a.setAttribute('href',rw(h));});
  });
})();
</script>`;
    html = html.replace('</head>', interceptor + '</head>');

    return new Response(html, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  return new Response(resp.body, { status: resp.status, headers: resp.headers });
}
