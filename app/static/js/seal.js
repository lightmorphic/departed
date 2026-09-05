/* Sealing and opening, done entirely in your browser.
 *
 * Files are put into an ordinary zip, then encrypted with AES-256-CBC using a
 * key stretched from your passphrase with PBKDF2. The container is byte for byte
 * what OpenSSL writes, so anyone who receives it can open it with one standard
 * command and does not need this program at all:
 *
 *   openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 \
 *     -in sealed.enc -out sealed.zip
 *
 * Nothing here is ever sent anywhere. The passphrase stays in this page.
 */
(function (global) {
  'use strict';

  var ITER = 600000;
  var MAGIC = 'Salted__';

  // ---- small helpers -------------------------------------------------

  function bytes(n) { return new Uint8Array(n); }

  function concat(parts) {
    var total = 0, i;
    for (i = 0; i < parts.length; i++) total += parts[i].length;
    var out = bytes(total), at = 0;
    for (i = 0; i < parts.length; i++) { out.set(parts[i], at); at += parts[i].length; }
    return out;
  }

  function u32(view, at, value) { view.setUint32(at, value, true); }

  var CRC_TABLE = (function () {
    var table = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(data) {
    var c = 0xffffffff;
    for (var i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  var utf8 = new TextEncoder();
  var fromUtf8 = new TextDecoder();

  function dosTime(d) {
    return ((d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() / 2)) & 0xffff;
  }
  function dosDate(d) {
    return (((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate()) & 0xffff;
  }

  async function deflate(data) {
    if (typeof global.CompressionStream !== 'function') return null;
    try {
      var stream = new Blob([data]).stream().pipeThrough(new global.CompressionStream('deflate-raw'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    } catch (e) {
      return null;
    }
  }

  async function inflate(data) {
    var stream = new Blob([data]).stream().pipeThrough(new global.DecompressionStream('deflate-raw'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  // ---- zip -----------------------------------------------------------

  async function zip(files) {
    var chunks = [], central = [], offset = 0;
    for (var i = 0; i < files.length; i++) {
      var name = utf8.encode(files[i].name);
      var raw = files[i].data;
      var crc = crc32(raw);
      var packed = await deflate(raw);
      var method = 0;
      if (packed && packed.length < raw.length) { method = 8; } else { packed = raw; }
      var when = files[i].modified || new Date();

      var local = bytes(30 + name.length);
      var lv = new DataView(local.buffer);
      u32(lv, 0, 0x04034b50);
      lv.setUint16(4, 20, true);            // version needed
      lv.setUint16(6, 0x0800, true);        // utf-8 names
      lv.setUint16(8, method, true);
      lv.setUint16(10, dosTime(when), true);
      lv.setUint16(12, dosDate(when), true);
      u32(lv, 14, crc);
      u32(lv, 18, packed.length);
      u32(lv, 22, raw.length);
      lv.setUint16(26, name.length, true);
      lv.setUint16(28, 0, true);
      local.set(name, 30);
      chunks.push(local, packed);

      var dir = bytes(46 + name.length);
      var dv = new DataView(dir.buffer);
      u32(dv, 0, 0x02014b50);
      dv.setUint16(4, 20, true);
      dv.setUint16(6, 20, true);
      dv.setUint16(8, 0x0800, true);
      dv.setUint16(10, method, true);
      dv.setUint16(12, dosTime(when), true);
      dv.setUint16(14, dosDate(when), true);
      u32(dv, 16, crc);
      u32(dv, 20, packed.length);
      u32(dv, 24, raw.length);
      dv.setUint16(28, name.length, true);
      u32(dv, 42, offset);
      dir.set(name, 46);
      central.push(dir);

      offset += local.length + packed.length;
    }
    var dirBytes = concat(central);
    var end = bytes(22);
    var ev = new DataView(end.buffer);
    u32(ev, 0, 0x06054b50);
    ev.setUint16(8, files.length, true);
    ev.setUint16(10, files.length, true);
    u32(ev, 12, dirBytes.length);
    u32(ev, 16, offset);
    return concat(chunks.concat([dirBytes, end]));
  }

  async function unzip(data) {
    var view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    var end = -1;
    for (var i = data.length - 22; i >= 0 && i > data.length - 66000; i--) {
      if (view.getUint32(i, true) === 0x06054b50) { end = i; break; }
    }
    if (end < 0) throw new Error('That does not look like a sealed archive.');
    var count = view.getUint16(end + 10, true);
    var at = view.getUint32(end + 16, true);
    var out = [];
    for (var n = 0; n < count; n++) {
      if (view.getUint32(at, true) !== 0x02014b50) throw new Error('The archive is damaged.');
      var method = view.getUint16(at + 10, true);
      var packedSize = view.getUint32(at + 20, true);
      var plainSize = view.getUint32(at + 24, true);
      var nameLen = view.getUint16(at + 28, true);
      var extraLen = view.getUint16(at + 30, true);
      var commentLen = view.getUint16(at + 32, true);
      var localAt = view.getUint32(at + 42, true);
      var name = fromUtf8.decode(data.subarray(at + 46, at + 46 + nameLen));

      var lNameLen = view.getUint16(localAt + 26, true);
      var lExtraLen = view.getUint16(localAt + 28, true);
      var start = localAt + 30 + lNameLen + lExtraLen;
      var body = data.subarray(start, start + packedSize);
      if (method === 8) body = await inflate(body);
      else if (method !== 0) throw new Error('The archive uses a compression this page cannot read.');
      if (body.length !== plainSize) throw new Error('The archive is damaged.');
      out.push({ name: name, data: body });
      at += 46 + nameLen + extraLen + commentLen;
    }
    return out;
  }

  // ---- the encryption ------------------------------------------------

  async function deriveKeyAndIv(passphrase, salt) {
    var base = await crypto.subtle.importKey('raw', utf8.encode(passphrase), 'PBKDF2', false, ['deriveBits']);
    var bits = await crypto.subtle.deriveBits(
      { name: 'PBKDF2', salt: salt, iterations: ITER, hash: 'SHA-256' }, base, 48 * 8);
    var all = new Uint8Array(bits);
    return {
      key: await crypto.subtle.importKey('raw', all.subarray(0, 32), 'AES-CBC', false, ['encrypt', 'decrypt']),
      iv: all.subarray(32, 48),
    };
  }

  async function seal(files, passphrase) {
    var plain = await zip(files);
    var salt = crypto.getRandomValues(bytes(8));
    var kv = await deriveKeyAndIv(passphrase, salt);
    var cipher = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-CBC', iv: kv.iv }, kv.key, plain));
    return concat([utf8.encode(MAGIC), salt, cipher]);
  }

  async function open(sealed, passphrase) {
    if (sealed.length < 24 || fromUtf8.decode(sealed.subarray(0, 8)) !== MAGIC) {
      throw new Error('That file was not sealed by Departed.');
    }
    var kv = await deriveKeyAndIv(passphrase, sealed.subarray(8, 16));
    var plain;
    try {
      plain = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-CBC', iv: kv.iv }, kv.key, sealed.subarray(16)));
    } catch (e) {
      throw new Error('That passphrase does not open this file.');
    }
    return unzip(plain);
  }

  // ---- base64 ---------------------------------------------------------

  function toBase64(data) {
    var out = '', chunk = 0x8000;
    for (var i = 0; i < data.length; i += chunk) {
      out += String.fromCharCode.apply(null, data.subarray(i, i + chunk));
    }
    return btoa(out);
  }

  function fromBase64(text) {
    var raw = atob(text.replace(/\s+/g, ''));
    var out = bytes(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }


  // ---- what the opener page is made of --------------------------------

  var OPENER_CSS = [
    ':root{color-scheme:light dark;--bg:#f7f4ef;--fg:#14161d;--soft:#4a5060;--muted:#5c6270;',
    '--panel:#fff;--line:rgba(24,24,40,.14);--accent:#fbc711;--on-accent:#443502;--ok:#2e6b30;--okbg:#eaf5ea;--bad:#a82c23;--badbg:#fdecea}',
    '@media(prefers-color-scheme:dark){:root{--bg:#0a0d14;--fg:#eceef4;--soft:#b4bac9;--muted:#8b91a3;',
    '--panel:#141824;--line:rgba(255,255,255,.12);--ok:#6fc973;--okbg:#122a14;--bad:#f4756b;--badbg:#2c100c}}',
    '*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);',
    'font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:2.5rem 1.25rem 4rem}',
    'main{max-width:34rem;margin:0 auto}h1{font-size:1.75rem;line-height:1.2;letter-spacing:-.02em;margin:0 0 .75rem}',
    'p{margin:0 0 1rem;color:var(--soft)}.lead{color:var(--fg);font-size:1.0625rem}',
    '.card{background:var(--panel);border:1px solid var(--line);border-radius:1rem;padding:1.5rem;margin:1.75rem 0}',
    'label{display:block;font-weight:600;color:var(--fg);margin:0 0 .5rem}',
    'input[type=password]{display:block;width:100%;font:inherit;min-height:2.75rem;padding:.625rem .875rem;',
    'border-radius:.75rem;border:1px solid var(--line);background:var(--bg);color:var(--fg)}',
    'button{font:inherit;font-weight:700;min-height:2.75rem;padding:.6875rem 1.375rem;border-radius:.75rem;',
    'border:1px solid var(--line);background:var(--panel);color:var(--fg);cursor:pointer}',
    'button.go{background:var(--accent);color:var(--on-accent);border-color:transparent;margin-top:1rem}',
    'button.small{min-height:2.25rem;padding:.375rem .875rem;font-size:.875rem}',
    'button:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}',
    '.msg{padding:.75rem 1rem;border-radius:.75rem;font-weight:600;margin:1.25rem 0 0}',
    '.msg.ok{background:var(--okbg);color:var(--ok)}.msg.bad{background:var(--badbg);color:var(--bad)}',
    'ul{list-style:none;margin:1.25rem 0 0;padding:0}',
    'li{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;padding:.75rem 0;border-top:1px solid var(--line)}',
    'li .n{flex:1;min-width:9rem;overflow-wrap:anywhere}li .s{font-size:.8125rem;color:var(--muted)}',
    'details{margin-top:2rem;border-top:1px solid var(--line);padding-top:1.25rem}',
    'summary{cursor:pointer;font-weight:600;min-height:2.75rem;display:flex;align-items:center}',
    'code,pre{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.8125rem}',
    'pre{background:var(--panel);border:1px solid var(--line);border-radius:.75rem;padding:1rem;overflow-x:auto;line-height:1.7}',
    '.foot{margin-top:2.5rem;font-size:.8125rem;color:var(--muted)}'
  ].join('');

  var OPENER_BODY = [
    '<main>',
    '<h1>Somebody has left you some files</h1>',
    '<p class="lead">They were locked before they were sent, and they were sealed on {{stamp}}. ',
    'You were given a passphrase. Type it in and you will get everything back.</p>',
    '<div class="card">',
    '<label for="p">The passphrase</label>',
    '<input id="p" type="password" autocomplete="off" spellcheck="false" autofocus>',
    '<button class="go" id="go" type="button">Open it</button>',
    '<div id="r"></div>',
    '<noscript><p class="msg bad">This page needs JavaScript. Open it in an ordinary web browser rather than a preview window.</p></noscript>',
    '</div>',
    '<p>Nothing here goes anywhere. This file does all the work on the computer you opened it on, and it works with no internet connection at all. Nobody is told that you opened it.</p>',
    '<details><summary>If you would rather not trust this page</summary>',
    '<p>You do not have to use it. Underneath, this is an ordinary encrypted file of the kind OpenSSL makes. Save it with the button below, then run this on any Mac or Linux machine, or in Git Bash on Windows.</p>',
    '<pre>openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 \\\n  -in sealed.enc -out inside.zip</pre>',
    '<p>It asks for the same passphrase, and out comes an ordinary zip file.</p>',
    '<button class="small" id="raw" type="button">Save the encrypted file</button>',
    '</details>',
    '<p class="foot">Made by Departed, a dead man&rsquo;s switch. If the passphrase does not work, check for a letter that should be a number. There is no l or o in it, so those will be a one and a zero.</p>',
    '</main>'
  ].join('\n');

  var OPENER_JS = [
    '(function(){',
    'var pass=document.getElementById("p"),go=document.getElementById("go"),out=document.getElementById("r");',
    'function say(k,t){out.innerHTML="";var p=document.createElement("p");p.className="msg "+k;',
    'p.setAttribute("role","status");p.textContent=(k==="ok"?"\\u2713 ":"! ")+t;out.appendChild(p);return p;}',
    'function readable(n){var u=["bytes","KB","MB","GB"];for(var i=0;i<u.length;i++){if(n<1024||i===3)',
    'return (i?n.toFixed(1):n)+" "+u[i];n/=1024;}}',
    'function save(name,data){var url=URL.createObjectURL(new Blob([data],{type:"application/octet-stream"}));',
    'var a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();',
    'setTimeout(function(){URL.revokeObjectURL(url);},4000);}',
    'var payload=Seal.fromBase64(document.getElementById("departed-payload").textContent);',
    'document.getElementById("raw").addEventListener("click",function(){save("sealed.enc",payload);});',
    'async function attempt(){',
    'if(!pass.value){return say("bad","Type the passphrase first.");}',
    'go.disabled=true;var was=go.textContent;go.textContent="Opening\\u2026";',
    'try{var inside=await Seal.open(payload,pass.value);',
    'say("ok","It opened. "+inside.length+" file"+(inside.length===1?"":"s")+" inside.");',
    'var list=document.createElement("ul");',
    'inside.forEach(function(f){var li=document.createElement("li");',
    'var n=document.createElement("span");n.className="n";n.textContent=f.name;',
    'var s=document.createElement("span");s.className="s";s.textContent=readable(f.data.length);',
    'var b=document.createElement("button");b.type="button";b.className="small";b.textContent="Save it";',
    'b.addEventListener("click",function(){save(f.name,f.data);});',
    'li.appendChild(n);li.appendChild(s);li.appendChild(b);list.appendChild(li);});',
    'out.appendChild(list);',
    'var all=document.createElement("button");all.type="button";all.className="go";all.textContent="Save them all";',
    'all.addEventListener("click",function(){inside.forEach(function(f,i){setTimeout(function(){save(f.name,f.data);},i*350);});});',
    'out.appendChild(all);',
    '}catch(e){say("bad",e.message);}',
    'go.disabled=false;go.textContent=was;}',
    'go.addEventListener("click",attempt);',
    'pass.addEventListener("keydown",function(e){if(e.key==="Enter")attempt();});',
    '})();'
  ].join('\n');

  // ---- the file that opens itself -------------------------------------

  var PAYLOAD_ID = 'departed-payload';

  /* Wraps the sealed bytes in a small web page. The person who receives it
   * double-clicks the file, types the passphrase, and gets their files back.
   * It works with no internet connection and on any computer with a browser. */
  function makeOpener(sealed, sealSource, when) {
    var stamp = (when || new Date()).toISOString().slice(0, 10);
    return '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
      + '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
      + '<title>Open me</title>\n<style>' + OPENER_CSS + '</style>\n</head>\n<body>\n'
      + OPENER_BODY.replace('{{stamp}}', stamp)
      + '\n<script id="' + PAYLOAD_ID + '" type="application/octet-stream">' + toBase64(sealed) + '<\/script>\n'
      + '<script>' + sealSource + '<\/script>\n'
      + '<script>' + OPENER_JS + '<\/script>\n</body>\n</html>\n';
  }

  /* Pulls the sealed bytes back out of one of those pages, so the person who
   * made it can change what is inside. */
  function payloadFrom(text) {
    var match = /id="departed-payload"[^>]*>([A-Za-z0-9+/=\s]+)</.exec(text);
    if (!match) return null;
    return fromBase64(match[1]);
  }

  // ---- passphrases ---------------------------------------------------

  // No letters or digits that get mistaken for one another when read aloud
  // or written down.
  var ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789';

  function makePassphrase(groups, size) {
    groups = groups || 6;
    size = size || 5;
    var picks = crypto.getRandomValues(bytes(groups * size));
    var out = [];
    for (var g = 0; g < groups; g++) {
      var word = '';
      for (var i = 0; i < size; i++) word += ALPHABET[picks[g * size + i] % ALPHABET.length];
      out.push(word);
    }
    return out.join('-');
  }

  global.Seal = {
    seal: seal,
    open: open,
    zip: zip,
    unzip: unzip,
    makePassphrase: makePassphrase,
    makeOpener: makeOpener,
    payloadFrom: payloadFrom,
    toBase64: toBase64,
    fromBase64: fromBase64,
    iterations: ITER,
  };
})(typeof window !== 'undefined' ? window : globalThis);
