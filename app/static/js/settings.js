/* The settings save themselves.
 *
 * Each box sends only itself, as soon as you have finished with it, and a small
 * tick appears beside its label for a moment. Nothing is lost by navigating away.
 */
(function () {
  'use strict';

  var forms = document.querySelectorAll('form.autosave');
  if (!forms.length || !window.fetch) return;

  function tickFor(field) {
    var label = document.querySelector('label[for="' + field.id + '"]');
    if (!label) return null;
    var tick = label.querySelector('.saved');
    if (!tick) {
      tick = document.createElement('span');
      tick.className = 'saved';
      tick.setAttribute('role', 'status');
      label.appendChild(tick);
    }
    return tick;
  }

  function say(field, text, bad) {
    var tick = tickFor(field);
    if (!tick) return;
    tick.textContent = text;
    tick.classList.toggle('bad', !!bad);
    tick.classList.add('on');
    clearTimeout(tick.timer);
    tick.timer = setTimeout(function () { tick.classList.remove('on'); }, bad ? 8000 : 2500);
  }

  async function save(field) {
    if (field.dataset.was === field.value) return;
    var body = new FormData();
    body.append('name', field.name);
    body.append('value', field.value);
    try {
      var res = await fetch('/settings/field', { method: 'POST', body: body });
      var out = await res.json();
      if (!out.ok) throw new Error(out.error || 'it would not save');
      field.dataset.was = field.value;
      if (!out.unchanged) say(field, '✓ Saved');
    } catch (e) {
      say(field, '! Not saved. ' + e.message, true);
    }
  }

  forms.forEach(function (form) {
    form.querySelectorAll('input[name], select[name], textarea[name]').forEach(function (field) {
      if (field.type === 'file') return;
      field.dataset.was = field.value;
      var later;
      field.addEventListener('input', function () {
        clearTimeout(later);
        later = setTimeout(function () { save(field); }, 900);
      });
      field.addEventListener('change', function () { clearTimeout(later); save(field); });
      field.addEventListener('blur', function () { clearTimeout(later); save(field); });
    });
  });

  /* "Use the address I am on now" */
  var here = document.getElementById('use-here');
  var box = document.getElementById('base_url');
  if (here && box) {
    here.addEventListener('click', function () {
      box.value = here.dataset.here;
      box.focus();
      save(box);
    });
  }

  /* The mail test */
  var test = document.getElementById('test-mail');
  var said = document.getElementById('test-mail-said');
  if (test && said) {
    test.addEventListener('click', async function () {
      test.disabled = true;
      var was = test.textContent;
      test.textContent = 'Sending...';
      said.textContent = '';
      said.className = 'hint';
      try {
        var res = await fetch('/settings/test-mail', { method: 'POST' });
        var out = await res.json();
        said.textContent = out.ok ? '✓ Sent to ' + out.sent_to + '. Go and look.'
                                  : '! ' + out.error;
        said.className = out.ok ? 'hint ok' : 'hint bad';
      } catch (e) {
        said.textContent = '! ' + e.message;
        said.className = 'hint bad';
      }
      test.disabled = false;
      test.textContent = was;
    });
  }
})();
