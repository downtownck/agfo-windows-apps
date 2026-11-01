"""Sahte sounddevice: mic_engine / arayuz testleri icin (ses aygiti gerektirmez)."""
import types


class FakeSD:
    """sounddevice'in kullanilan yuzeyi. fail(stream_kwargs) True donerse akis acilisi hata verir."""

    def __init__(self, fail=None, apis=('MME', 'Windows WASAPI')):
        self.fail = fail or (lambda kw: False)
        self.opened = []
        self.apis = []
        self.devs = []
        for ai, name in enumerate(apis):
            base = len(self.devs)
            self.devs += [
                dict(name='Mikrofon (Realtek(R) Audio)', hostapi=ai, max_input_channels=2, max_output_channels=0, default_samplerate=48000.0),
                dict(name='Kulaklık (Realtek(R) Audio)', hostapi=ai, max_input_channels=0, max_output_channels=2, default_samplerate=48000.0),
                dict(name='Hoparlör (Realtek(R) Audio)', hostapi=ai, max_input_channels=0, max_output_channels=2, default_samplerate=44100.0),
            ]
            self.apis.append(dict(name=name, default_input_device=base, default_output_device=base + 2))
        self.default = types.SimpleNamespace(hostapi=0)
        sd = self

        class WasapiSettings:
            def __init__(self, exclusive=False, auto_convert=False, explicit_sample_format=False):
                self._streaminfo = types.SimpleNamespace(flags=(1 if exclusive else 0) | (64 if auto_convert else 0),
                                                         streamOption=0)

        class _S:
            kind = 'duplex'

            def __init__(self, **kw):
                self.kw = kw
                if sd.fail(dict(kw, kind=self.kind)):
                    raise RuntimeError('Error opening %s: Invalid device / exclusive mode refused' % self.kind)
                self.callback = kw['callback']
                self.finished = kw.get('finished_callback')
                self.active = False
                lat = kw['latency']
                self.latency = lat if self.kind != 'duplex' else tuple(lat)
                sd.opened.append(self)

            def start(self):
                self.active = True

            def abort(self):
                self.active = False

            def close(self):
                self.active = False

        class Stream(_S):
            kind = 'duplex'

        class InputStream(_S):
            kind = 'input'

        class OutputStream(_S):
            kind = 'output'

        self.WasapiSettings, self.Stream, self.InputStream, self.OutputStream = WasapiSettings, Stream, InputStream, OutputStream

    def query_hostapis(self, index=None):
        return self.apis if index is None else self.apis[index]

    def query_devices(self, index=None):
        return self.devs if index is None else self.devs[index]
