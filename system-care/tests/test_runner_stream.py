"""Regresyon: Runner akis ayristirici - BOM, \r ilerleme kareleri, NUL, UTF-8, @@JSON veri satirlari, bozuk veri uyarisi, cikis kodu.
python -I tests/test_runner_stream.py <agfo-care klasoru>"""
import importlib.machinery, importlib.util, pathlib, queue, sys, tempfile, types
ROOT = pathlib.Path(sys.argv[1])
tk = types.ModuleType('tkinter'); tk.Tk = object; tk.Frame = object; tk.Canvas = object
for m in ('ttk', 'filedialog', 'messagebox'):
    mod = types.ModuleType('tkinter.' + m); setattr(tk, m, mod); sys.modules['tkinter.' + m] = mod
sys.modules['tkinter.ttk'].Frame = object
sys.modules['tkinter'] = tk
spec = importlib.util.spec_from_file_location('agfo_app', ROOT / 'app.pyw', loader=importlib.machinery.SourceFileLoader('agfo_app', str(ROOT / 'app.pyw')))
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
tmp = pathlib.Path(tempfile.mkdtemp()); app.LOG_DIR = tmp / 'logs'
em = tmp / 'emit.py'
em.write_text("import sys,time\nw=sys.stdout.buffer\nw.write(b'\\xef\\xbb\\xbfBaslik\\n')\n"
              "for i in range(0,101,25): w.write(('[== %3d%% ==]\\r'%i).encode()); w.flush(); time.sleep(0.03)\n"
              "w.write(b'\\n@@{\"type\":\"device\",\"name\":\"Ayg\\xc4\\xb1t\",\"id\":\"PCI\\\\\\\\VEN\"}\\n')\n"
              "w.write(b'@@{bozuk\\n')\nw.write(b'S\\x00F\\x00C ok \\xc3\\xbc\\n')\nw.write(b'kuyruk')\nsys.exit(7)\n", encoding='utf-8')
q = queue.Queue()
r = app.Runner(q.put)
job = app.Job('test', cmd=[sys.executable, '-I', str(em)])
r._run_all([job])
ev = []
while not q.empty(): ev.append(q.get())
lines = [v for k, v in ev if k == 'line']
prog = [v for k, v in ev if k == 'progress']
assert job.code == 7, job.code
assert job.lines[0] == 'Baslik' and '[== 100% ==]' in job.lines and 'SFC ok ü' in job.lines and job.lines[-1] == 'kuyruk', job.lines
assert job.data == [{'type': 'device', 'name': 'Aygıt', 'id': 'PCI\\VEN'}], job.data
assert any(l.startswith('Uyarı: okunamayan veri satırı') for l in job.lines), job.lines
assert not any(l.startswith('@@{"type"') for l in lines), 'veri satiri gunluge sizmamali'
assert prog, 'canli ilerleme bekleniyordu'
log = pathlib.Path(job.logfile).read_text(encoding='utf-8')
assert log.count('==]') == 1, log
assert ('alldone', None) in ev and any(k == 'jobdone' for k, _ in ev)
# zincir: stop olayi sonraki isleri atlar
q2 = queue.Queue(); r2 = app.Runner(q2.put); r2.stop.set()
j1 = app.Job('a', func=lambda rr, jj: 0)
r2.stop.clear()
def stopper(rr, jj):
    rr.stop.set(); return 0
j0 = app.Job('stop', func=stopper)
r2._run_all([j0, j1])
assert j0.code == 0 and j1.code is None, (j0.code, j1.code)
print('PASS runner-stream: %d satir, %d ilerleme, veri=%d, cikis=%d; zincir durdurma OK' % (len(job.lines), len(prog), len(job.data), job.code))
