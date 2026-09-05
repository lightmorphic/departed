/* Opening a sealed archive. Runs in the browser and sends nothing anywhere. */
(function () {
  'use strict';
  var file = document.getElementById('sealed-file');
  var pass = document.getElementById('sealed-pass');
  var button = document.getElementById('open-it');
  var out = document.getElementById('open-result');
  if (!file || !button || !window.Seal) return;

  function say(kind, text) {
    out.innerHTML = '';
    var p = document.createElement('p');
    p.className = 'tint ' + kind;
    p.setAttribute('role', 'status');
    p.textContent = (kind === 'success' ? '✓ ' : '! ') + text;
    out.appendChild(p);
    return p;
  }

  function readable(n) {
    var units = ['bytes', 'KB', 'MB', 'GB'];
    for (var i = 0; i < units.length; i++) {
      if (n < 1024 || i === 3) return (i ? n.toFixed(1) : n) + ' ' + units[i];
      n /= 1024;
    }
  }

  function save(name, data) {
    var url = URL.createObjectURL(new Blob([data], { type: 'application/octet-stream' }));
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  button.addEventListener('click', async function () {
    if (!file.files.length) return say('warning', 'Choose the file first.');
    if (!pass.value) return say('warning', 'Type the passphrase.');
    button.disabled = true;
    var was = button.textContent;
    button.textContent = 'Opening...';
    try {
      var raw = new Uint8Array(await file.files[0].arrayBuffer());
      var sealed = raw;
      if (!(raw.length > 8 && String.fromCharCode.apply(null, raw.subarray(0, 8)) === 'Salted__')) {
        var found = Seal.payloadFrom(new TextDecoder().decode(raw));
        if (!found) throw new Error('That file does not hold a sealed archive.');
        sealed = found;
      }
      var inside = await Seal.open(sealed, pass.value);
      say('success', 'It opened. ' + inside.length + ' file' + (inside.length === 1 ? '' : 's') + ' inside.');
      var list = document.createElement('ul');
      list.className = 'files';
      inside.forEach(function (f) {
        var li = document.createElement('li');
        var name = document.createElement('span');
        name.textContent = f.name;
        var size = document.createElement('span');
        size.className = 'hint';
        size.textContent = readable(f.data.length);
        var get = document.createElement('button');
        get.type = 'button';
        get.className = 'btn small';
        get.textContent = 'Save it';
        get.addEventListener('click', function () { save(f.name, f.data); });
        li.appendChild(name); li.appendChild(size); li.appendChild(get);
        list.appendChild(li);
      });
      out.appendChild(list);
      var all = document.createElement('button');
      all.type = 'button';
      all.className = 'btn primary';
      all.textContent = 'Save them all';
      all.addEventListener('click', function () {
        inside.forEach(function (f, i) { setTimeout(function () { save(f.name, f.data); }, i * 350); });
      });
      var actions = document.createElement('div');
      actions.className = 'actions';
      actions.appendChild(all);
      out.appendChild(actions);
    } catch (e) {
      say('danger', e.message);
    }
    button.disabled = false;
    button.textContent = was;
  });
})();
