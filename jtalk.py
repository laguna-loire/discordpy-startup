import subprocess
import os
import asyncio
import discord
import threading
import torch
import io

from tts.jtalkCore import libjt_initialize, g2p
from tts.mecab import Mecab_initialize, MecabFeatures, Mecab_analysis
from tts.text2mecab import text2mecab

def get_normalization_factor(max_abs_value, normalize):
    if not normalize and max_abs_value > 1:
        raise ValueError('Audio data must be between -1 and 1 when normalize=False.')
    return max_abs_value if normalize else 1

def validate_and_normalize_with_numpy(data, normalize):
    import numpy as np

    data = np.array(data, dtype=float)
    if len(data.shape) == 1:
        nchan = 1
    elif len(data.shape) == 2:
        # In wave files,channels are interleaved. E.g.,
        # "L1R1L2R2..." for stereo. See
        # http://msdn.microsoft.com/en-us/library/windows/hardware/dn653308(v=vs.85).aspx
        # for channel ordering
        nchan = data.shape[0]
        data = data.T.ravel()
    else:
        raise ValueError('Array audio input must be a 1D or 2D array')
    
    max_abs_value = np.max(np.abs(data))
    normalization_factor = get_normalization_factor(max_abs_value, normalize)
    scaled = np.int16(data / normalization_factor * 32767).tolist()
    return scaled, nchan

def validate_and_normalize_without_numpy(data, normalize):
    try:
        max_abs_value = float(max([abs(x) for x in data]))
    except TypeError:
        raise TypeError('Only lists of mono audio are '
            'supported if numpy is not installed')

    normalization_factor = get_normalization_factor(max_abs_value, normalize)
    scaled = [int(x / normalization_factor * 32767) for x in data]
    nchan = 1
    return scaled, nchan

def make_wav(data, rate, normalize):
    """ Transform a numpy array to a PCM bytestring """
    import struct
    from io import BytesIO
    import wave

    try:
        scaled, nchan = validate_and_normalize_with_numpy(data, normalize)
    except ImportError:
        scaled, nchan = validate_and_normalize_without_numpy(data, normalize)

    fp = BytesIO()
    waveobj = wave.open(fp,mode='wb')
    waveobj.setnchannels(nchan)
    waveobj.setframerate(rate)
    waveobj.setsampwidth(2)
    waveobj.setcomptype('NONE','NONE')
    waveobj.writeframes(b''.join([struct.pack('<h',x) for x in scaled]))
    val = fp.getvalue()
    waveobj.close()

    return val
class Esp:
    device = None
    model = None
    inference_args = None
    config = None
    vocoder = None
    char_to_id = None
    idim = None
    
    def __init__(self):
        # set path
        dict_path = "./tts/data/train_no_dev_units.txt"
        model_path = "./tts/data/model.last1.avg.best"
        vocoder_path = "./tts/data/checkpoint-400000steps.pkl"
        vocoder_conf = "./tts/data/config.yml"

        # define device
        import torch
        self.device = torch.device("cpu")

        # define E2E-TTS model
        from argparse import Namespace
        from espnet.asr.asr_utils import get_model_conf
        from espnet.asr.asr_utils import torch_load
        from espnet.utils.dynamic_import import dynamic_import
        self.idim, odim, train_args = get_model_conf(model_path)
        model_class = dynamic_import(train_args.model_module)
        self.model = model_class(self.idim, odim, train_args)
        torch_load(model_path, self.model)
        self.model = self.model.eval().to(self.device)
        self.inference_args = Namespace(**{"threshold": 0.5, "minlenratio": 0.0, "maxlenratio": 10.0})

        # define neural vocoder
        import yaml
        from parallel_wavegan.models import ParallelWaveGANGenerator
        with open(vocoder_conf) as f:
            self.config = yaml.load(f, Loader=yaml.Loader)
        self.vocoder = ParallelWaveGANGenerator(**self.config["generator_params"])
        self.vocoder.load_state_dict(torch.load(vocoder_path, map_location="cpu")["model"]["generator"])
        self.vocoder.remove_weight_norm()
        self.vocoder = self.vocoder.eval().to(self.device)

        # define text frontend
        with open(dict_path) as f:
            lines = f.readlines()
        lines = [line.replace("\n", "").split(" ") for line in lines]
        self.char_to_id = {c: int(i) for c, i in lines}

        # jtalk
        libjt_initialize(os.path.abspath('./tts/libs/' + os.environ['JTALK_LIB']))
        Mecab_initialize(os.environ['MECAB_DIC'])

    def frontend(self, text):
        """Clean text and then convert to id sequence."""
        mf = MecabFeatures()
        s = text2mecab(text)
        Mecab_analysis(s, mf)
        text = g2p(mf.feature, mf.size)
        charseq = text.split(" ")
        idseq = []
        for c in charseq:
            if c.isspace():
                idseq += [self.char_to_id["<space>"]]
            elif c not in self.char_to_id.keys():
                idseq += [self.char_to_id["<unk>"]]
            else:
                idseq += [self.char_to_id[c]]
        idseq += [self.idim - 1]  # <eos>
        return torch.LongTensor(idseq).view(-1).to(self.device)
    
    def talk(self, text):
        with torch.no_grad():
            x = self.frontend(text)
            c, _, _ = self.model.inference(x, self.inference_args)
            z = torch.randn(1, 1, c.size(0) * self.config["hop_size"]).to(self.device)
            c = torch.nn.ReplicationPad1d(self.config["generator_params"]["aux_context_window"])(c.unsqueeze(0).transpose(2, 1))
            y = self.vocoder(z, c).view(-1)
        return make_wav(y.view(-1).cpu().numpy(), self.config["sampling_rate"], True)

class Jtalk:
    __lock = threading.Lock()
    loop = None
    voice_dict = dict()
    ch_dict = dict()
    esp = Esp()

    def clear(self):
        self.voice_dict.clear()
        self.ch_dict.clear()

    async def connect(self, author):
        await self.disconnect(author.id)
        if author.voice == None:
            return None
        voice = None
        if author.id in self.voice_dict:
            voice = self.ch_dict[self.voice_dict[author.id]]
        else:
            self.voice_dict[author.id] = author.voice.channel.id
            if author.voice.channel.id in self.ch_dict:
                voice = self.ch_dict[author.voice.channel.id]
            else:
                voice = await author.voice.channel.connect()
                self.ch_dict[author.voice.channel.id] = voice
        return voice
    
    async def disconnect(self, author_id):
        if author_id in self.voice_dict:
            voice_id = self.voice_dict[author_id]
            del self.voice_dict[author_id]
            for v in self.voice_dict.values():
                if v == voice_id:
                    return
            voice = self.ch_dict[voice_id]
            await voice.disconnect(force=True)
            del self.ch_dict[voice_id]
    
    def talk_ai(self, t, author):
        if author.id in self.voice_dict:
            voice = self.ch_dict[self.voice_dict[author.id]]
            output = './wav/' + str(author.id) + '.wav'
            asyncio.ensure_future(self.taco2_wavegan(t, voice, output), loop=self.loop)
    
    async def taco2_wavegan(self, t, voice, output):
        data = self.esp.talk(t)
        with open(output, mode='wb') as fout:
            fout.write(data)
        source = discord.FFmpegPCMAudio(output)
        await self.play(voice, source)
        os.remove(output)

    def talk(self, t, author, htsvoice=0):
        if author.id in self.voice_dict:
            voice = self.ch_dict[self.voice_dict[author.id]]
            wav = './wav/' + str(author.id) + '.wav'
            asyncio.ensure_future(self.jtalk(t, wav, voice, htsvoice), loop=self.loop)

    async def jtalk(self, t, output, voice, htsvoice):
        
        open_jtalk=[os.environ['JTALK']]
        mech=['-x',os.environ['JTALK_DIC']]
        htsvoice=['-m','./voice/' + str(htsvoice) + '.htsvoice']
        speed=['-r','1.0']
        outwav=['-ow',output]
        cmd=open_jtalk+mech+htsvoice+speed+outwav
        c = subprocess.Popen(cmd,stdin=subprocess.PIPE)
        c.stdin.write(t.encode(os.environ['JTALK_ENCODE']))
        c.stdin.close()
        c.wait()

        source = discord.FFmpegPCMAudio(output)
        await self.play(voice, source)
        os.remove(output)
        
    async def play(self, voice, source):
        self.__lock.acquire()
        voice.play(source, after=lambda e : self.__lock.release())
        count = 0
        while voice.is_playing():
            await asyncio.sleep(0.1)
            count += 1
            if count > 600:
                break