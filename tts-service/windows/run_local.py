"""AGFO TTS Service - Windows (yerel bilgisayar) baslaticisi.

.env dosyasini okur, ciktiyi service.log'a yazar ve servisi yalniz bu bilgisayardan erisilebilen
127.0.0.1 adresinde calistirir. Ayni anda tek kopya calisir. Konsolda gormek icin:  python run_local.py --console
"""
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    load_env(os.path.join(HERE, '.env'))
    os.environ.setdefault('HF_HOME', os.path.join(HERE, 'hf'))
    os.environ.setdefault('AGFO_TTS_CACHE_DIR', os.path.join(HERE, 'cache'))
    os.environ.setdefault('AGFO_TTS_DATA_DIR', os.path.join(HERE, 'data'))
    port = int(os.environ.get('AGFO_TTS_PORT', '8765'))
    if '--console' not in sys.argv:
        log_path = os.path.join(HERE, 'service.log')
        try:
            if os.path.getsize(log_path) > 5 * 1024 * 1024:
                os.replace(log_path, log_path + '.1')
        except OSError:
            pass
        log = open(log_path, 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    if port_in_use(port):
        print('Port %d zaten kullanimda; servis zaten calisiyor olabilir. Cikiliyor.' % port, flush=True)
        return 0
    os.chdir(HERE)
    sys.path.insert(0, HERE)
    import uvicorn
    import server
    print('AGFO TTS Service %s - 127.0.0.1:%d' % (server.app.version, port), flush=True)
    uvicorn.run(server.app, host='127.0.0.1', port=port, log_level='info', access_log=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
