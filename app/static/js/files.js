/* The sealing panel on the settings page.
 *
 * Everything here happens in this browser. Files are read locally, zipped and
 * encrypted here, and only the sealed result is sent to the server. The
 * passphrase is never sent, never stored and never logged.
 */
(function () {
  'use strict';

  var block = document.querySelector('.sealed-block');
  if (!block || !window.Seal || !window.crypto || !crypto.subtle) return;

  var panel = block.querySelector('.seal-panel');
  var picked = [];      // files waiting to be sealed
  var existing = [];    // what was already inside, once opened

  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') node.textContent = attrs[k];
      else if (k === 'html') node.innerHTML = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (kid) { node.appendChild(kid); });
    return node;
  }

  function show(nodes) {
    panel.innerHTML = '';
    nodes.forEach(function (n) { panel.appendChild(n); });
    panel.hidden = false;
    panel.scrollIntoView({ block: 'nearest' });
  }

  function note(kind, text) {
    return el('p', { 'class': 'tint ' + kind, text: (kind === 'success' ? '✓ ' : '! ') + text, role: 'status' });
  }

  function readable(n) {
    var units = ['bytes', 'KB', 'MB', 'GB'];
    for (var i = 0; i < units.length; i++) {
      if (n < 1024 || i === 3) return (i ? n.toFixed(1) : n) + ' ' + units[i];
      n /= 1024;
    }
  }

  function busy(button, on, label) {
    button.disabled = on;
    if (on) { button.dataset.was = button.textContent; button.textContent = label; }
    else if (button.dataset.was) { button.textContent = button.dataset.was; }
  }

  // ---- the list of files waiting to go in --------------------------------

  function fileList(items, onRemove) {
    var list = el('ul', { 'class': 'files' });
    items.forEach(function (f, i) {
      var row = el('li', {}, [
        el('span', { text: f.name }),
        el('span', { 'class': 'hint', text: readable(f.data ? f.data.length : f.size) }),
      ]);
      var remove = el('button', { type: 'button', 'class': 'btn danger small', text: 'Remove' });
      remove.addEventListener('click', function () { onRemove(i); });
      row.appendChild(remove);
      list.appendChild(row);
    });
    return list;
  }

  async function readFile(file) {
    return { name: file.name, data: new Uint8Array(await file.arrayBuffer()) };
  }

  // ---- making a new sealed archive ---------------------------------------

  function sealForm(startWith, passphrase) {
    existing = startWith || [];
    picked = [];

    function render() {
      var all = existing.concat(picked);
      var nodes = [el('h3', { 'class': 'sub-h', text: passphrase ? 'Change what is inside' : 'Seal some files' })];

      if (all.length) {
        nodes.push(fileList(all, function (i) {
          if (i < existing.length) existing.splice(i, 1);
          else picked.splice(i - existing.length, 1);
          render();
        }));
      } else {
        nodes.push(el('p', { 'class': 'hint', text: 'Nothing chosen yet.' }));
      }

      var input = el('input', { type: 'file', multiple: 'multiple', id: 'seal-files' });
      input.addEventListener('change', async function () {
        for (var i = 0; i < input.files.length; i++) picked.push(await readFile(input.files[i]));
        render();
      });
      nodes.push(el('label', { 'class': 'field', 'for': 'seal-files', text: 'Add files' }), input);

      var passBox = null;
      if (!passphrase) {
        nodes.push(el('label', { 'class': 'field', 'for': 'seal-pass', text: 'Passphrase' }));
        passBox = el('input', { type: 'text', id: 'seal-pass', autocomplete: 'off', spellcheck: 'false' });
        passBox.value = Seal.makePassphrase();
        nodes.push(passBox);
        var again = el('button', { type: 'button', 'class': 'btn small', text: 'Give me another' });
        again.addEventListener('click', function () { passBox.value = Seal.makePassphrase(); });
        nodes.push(el('p', { 'class': 'hint', text: 'Made here, in your browser. Change it to something of your own if you would rather. It is never sent anywhere, and once you leave this page nothing can tell you what it was.' }));
        nodes.push(el('div', { 'class': 'actions' }, [again]));
      }

      var go = el('button', { type: 'button', 'class': 'btn primary', text: passphrase ? 'Seal it again' : 'Seal and save' });
      var cancel = el('button', { type: 'button', 'class': 'btn', text: 'Cancel' });
      cancel.addEventListener('click', function () { panel.hidden = true; panel.innerHTML = ''; });

      go.addEventListener('click', async function () {
        var all2 = existing.concat(picked);
        if (!all2.length) return show(nodes.concat([note('warning', 'Choose at least one file first.')]));
        var pass = passphrase || (passBox && passBox.value.trim());
        if (!pass || pass.length < 8) return show(nodes.concat([note('warning', 'Use a passphrase of at least 8 characters.')]));
        busy(go, true, 'Sealing...');
        try {
          var sealed = await Seal.seal(all2, pass);
          await upload(sealed);
          done(pass, all2, !passphrase);
        } catch (e) {
          busy(go, false);
          show(nodes.concat([note('danger', 'That did not work: ' + e.message)]));
        }
      });

      nodes.push(el('div', { 'class': 'actions' }, [go, cancel]));
      show(nodes);
    }
    render();
  }

  async function upload(sealed) {
    var form = new FormData();
    form.append('sealed', new Blob([sealed], { type: 'application/octet-stream' }), 'departed-sealed.enc');
    var res = await fetch('/files/sealed', { method: 'POST', body: form });
    if (!res.ok) throw new Error('the server would not take it (' + res.status + ')');
  }

  function done(pass, all, showPass) {
    var nodes = [note('success', 'Sealed and saved. ' + all.length + ' file' + (all.length === 1 ? '' : 's') + ' inside.')];
    if (showPass) {
      nodes.push(el('h3', { 'class': 'sub-h', text: 'Write this down now' }));
      nodes.push(el('p', { 'class': 'hint', text: 'This is the only time it will ever be shown. Departed did not keep a copy and cannot get it back for you. Without it the archive is a locked box, for you and for everyone else.' }));
      var code = el('p', { 'class': 'passphrase', text: pass });
      nodes.push(code);
      var copy = el('button', { type: 'button', 'class': 'btn', text: 'Copy it' });
      copy.addEventListener('click', function () {
        navigator.clipboard.writeText(pass).then(function () { copy.textContent = 'Copied'; });
      });
      var printIt = el('button', { type: 'button', 'class': 'btn', text: 'Print it' });
      printIt.addEventListener('click', function () { window.print(); });
      nodes.push(el('div', { 'class': 'actions' }, [copy, printIt]));
      nodes.push(el('p', { 'class': 'hint', text: 'Your person needs this passphrase and nothing else. Give it to them in person rather than by email or message.' }));
    }
    var reload = el('button', { type: 'button', 'class': 'btn primary', text: 'Done' });
    reload.addEventListener('click', function () { location.href = '/settings?done=sealed'; });
    nodes.push(el('div', { 'class': 'actions' }, [reload]));
    show(nodes);
  }

  // ---- opening what is already there -------------------------------------

  function askPassphrase(title, then) {
    var input = el('input', { type: 'password', id: 'open-pass', autocomplete: 'off' });
    var go = el('button', { type: 'button', 'class': 'btn primary', text: 'Open it' });
    var cancel = el('button', { type: 'button', 'class': 'btn', text: 'Cancel' });
    cancel.addEventListener('click', function () { panel.hidden = true; panel.innerHTML = ''; });
    var nodes = [
      el('h3', { 'class': 'sub-h', text: title }),
      el('label', { 'class': 'field', 'for': 'open-pass', text: 'Your passphrase' }),
      input,
      el('p', { 'class': 'hint', text: 'Typed here and used here. It is not sent to the server.' }),
      el('div', { 'class': 'actions' }, [go, cancel]),
    ];
    async function attempt() {
      busy(go, true, 'Opening...');
      try {
        var res = await fetch('/files/sealed');
        if (!res.ok) throw new Error('the sealed archive could not be fetched');
        var sealed = new Uint8Array(await res.arrayBuffer());
        var inside = await Seal.open(sealed, input.value);
        then(inside, input.value);
      } catch (e) {
        busy(go, false);
        show(nodes.concat([note('danger', e.message)]));
        panel.querySelector('#open-pass').focus();
      }
    }
    go.addEventListener('click', attempt);
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') attempt(); });
    show(nodes);
    input.focus();
  }

  // ---- the buttons -------------------------------------------------------

  block.addEventListener('click', function (e) {
    var button = e.target.closest('[data-seal-action]');
    if (!button) return;
    var action = button.dataset.sealAction;

    if (action === 'new') return sealForm([], null);

    if (action === 'edit') {
      return askPassphrase('Change what is inside', function (inside, pass) {
        sealForm(inside, pass);
      });
    }

    if (action === 'check') {
      return askPassphrase('Check I can still open it', function (inside) {
        var nodes = [
          note('success', 'It opened. ' + inside.length + ' file' + (inside.length === 1 ? '' : 's') + ' inside, and this is all of it.'),
          fileList(inside, function () {}),
          el('p', { 'class': 'hint', text: 'Nothing was changed and nothing left this browser.' }),
        ];
        nodes[1].querySelectorAll('button').forEach(function (b) { b.remove(); });
        var close = el('button', { type: 'button', 'class': 'btn', text: 'Close' });
        close.addEventListener('click', function () { panel.hidden = true; panel.innerHTML = ''; });
        nodes.push(el('div', { 'class': 'actions' }, [close]));
        show(nodes);
      });
    }
  });
})();
