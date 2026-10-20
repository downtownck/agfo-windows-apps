import numpy as np, soundfile as sf
SAID=[]
class EMA:
    def say(self, text, path, speed=1.0, seed=0):
        SAID.append(text); sf.write(path, np.zeros(2400, dtype="float32"), 24000)
