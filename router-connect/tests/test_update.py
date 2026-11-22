import os, sys, tempfile, pathlib
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else '.')
import router_update as u

d = pathlib.Path(tempfile.mkdtemp())
src, tgt = d / 'new.exe', d / 'sub' / 'app.exe'
src.write_bytes(b'NEW')
u.replace_target(src, tgt, sleep=lambda s: None)
assert tgt.read_bytes() == b'NEW' and not (tgt.parent / 'app.exe.new').exists()
tgt.write_bytes(b'OLD')
u.replace_target(src, tgt, sleep=lambda s: None)
assert tgt.read_bytes() == b'NEW'
calls = []
class P:  # sahte Popen
    def __init__(self, cmd, **kw): calls.append(cmd)
u.apply_update(src, popen=P, pid=123, target=tgt)
assert calls[0][1:5] == ['--apply-update', str(tgt), '--wait-pid', '123'], calls
assert u.asset_pattern() == u.GH_ASSET
print('UPDATE OK')
