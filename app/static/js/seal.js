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
    iterations: ITER,
  };
})(typeof window !== 'undefined' ? window : globalThis);
