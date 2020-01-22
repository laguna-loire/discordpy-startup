import subprocess
import os
import asyncio
import discord
import threading

class Jtalk:
    __lock = threading.Lock()
    loop = None
    voice_dict = dict()
    ch_dict = dict()

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

    def talk(self, t, author):
        if author.id in self.voice_dict:
            voice = self.ch_dict[self.voice_dict[author.id]]
            wav = './wav/' + str(author.id) + '.wav'
            asyncio.ensure_future(self.jtalk(t, wav, voice), loop=self.loop)

    async def jtalk(self, t, output, voice):
        
        open_jtalk=[os.environ['JTALK']]
        mech=['-x',os.environ['JTALK_DIC']]
        htsvoice=['-m','./voice/mai.htsvoice']
        speed=['-r','1.0']
        outwav=['-ow',output]
        cmd=open_jtalk+mech+htsvoice+speed+outwav
        c = subprocess.Popen(cmd,stdin=subprocess.PIPE)
        c.stdin.write(t.encode(os.environ['JTALK_ENCODE']))
        c.stdin.close()
        c.wait()

        source = discord.FFmpegPCMAudio(output)
        #self.__lock.acquire()
        await self.play(voice, source)
        #self.__lock.release()
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