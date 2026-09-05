"""The sealing code is shared between the app and the website. It must not drift,
and the container it makes must be openable with plain openssl."""
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_the_website_ships_the_same_sealing_code():
    for name in ("seal.js", "open.js"):
        a = (ROOT / "app" / "static" / "js" / name).read_bytes()
        b = (ROOT / "docs" / "js" / name).read_bytes()
        assert a == b, f"{name} has drifted between the app and the website"


def test_a_sealed_archive_opens_with_plain_openssl(tmp_path):
    node = shutil.which("node")
    openssl = shutil.which("openssl")
    if not node or not openssl:
        import pytest
        pytest.skip("needs node and openssl")

    script = tmp_path / "check.mjs"
    script.write_text(f'''
import fs from 'node:fs';
new Function(fs.readFileSync({str(ROOT / "app/static/js/seal.js")!r}, 'utf8'))();
const S = globalThis.Seal;
const enc = new TextEncoder();
const files = [{{ name: 'note.txt', data: enc.encode('the thing itself') }}];
const sealed = await S.seal(files, 'a-test-passphrase');
fs.writeFileSync({str(tmp_path / "sealed.enc")!r}, sealed);
const back = await S.open(sealed, 'a-test-passphrase');
if (new TextDecoder().decode(back[0].data) !== 'the thing itself') throw new Error('round trip failed');
let refused = false;
try {{ await S.open(sealed, 'wrong'); }} catch (e) {{ refused = true; }}
if (!refused) throw new Error('a wrong passphrase was accepted');
console.log('ok');
''')
    out = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout

    plain = tmp_path / "inside.zip"
    subprocess.run([openssl, "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",
                    "-md", "sha256", "-pass", "pass:a-test-passphrase",
                    "-in", str(tmp_path / "sealed.enc"), "-out", str(plain)], check=True)
    import zipfile
    with zipfile.ZipFile(plain) as z:
        assert z.namelist() == ["note.txt"]
        assert z.read("note.txt") == b"the thing itself"
