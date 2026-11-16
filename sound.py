from pathlib import Path

from ursina import Audio, invoke

AUDIO_DIR = Path(__file__).resolve().parent / "audio"
EXTS = (".wav", ".ogg", ".mp3")

SFX_VOLUME = {
    "click": 0.6, "start": 0.8, "slash": 0.7, "palm": 0.9, "water": 0.9,
    "extinguish": 1.0, "hit": 1.0, "info": 0.8, "win": 1.0, "lose": 1.0,
}
MUSIC_VOLUME = {"menu": 0.45, "game": 0.40}


def _find(stem):
    for ext in EXTS:
        p = AUDIO_DIR / f"{stem}{ext}"
        if p.exists():
            return p
    return None


class SoundManager:
    def __init__(self, state):
        self.S = state                  
        self.tracks = {}                
        self.current = None             
        self.pitch = 1.0

    #musik
    def _track(self, name):
        if name not in self.tracks:
            p = _find(f"music_{name}")
            a = None
            if p is not None:
                try:
                    a = Audio(p, loop=True, autoplay=False,
                            volume=MUSIC_VOLUME.get(name, 0.4), group="music")
                except Exception as e:
                    print("[sound] gagal memuat musik", name, e)
            self.tracks[name] = a
        return self.tracks[name]

    def music(self, name):
        """Pilih musik latar. Aman dipanggil berulang dengan nama yang sama."""
        self.current = name
        for n, a in self.tracks.items():
            if n != name and a is not None:
                a.stop(destroy=False)
        if name is None or not self.S.music:
            return
        a = self._track(name)
        if a is not None and not a.playing:
            a.pitch = self.pitch
            a.play()

    def stop_music(self):
        self.music(None)

    def set_music_pitch(self, pitch):
        """Ubah kecepatan/nada musik (dipakai saat efek air aktif)."""
        if pitch == self.pitch:
            return
        self.pitch = pitch
        a = self.tracks.get(self.current)
        if a is not None:
            a.pitch = pitch

    def sync(self):
        """Panggil setelah toggle Music berubah di Settings."""
        if not self.S.music:
            for a in self.tracks.values():
                if a is not None:
                    a.stop(destroy=False)
        else:
            self.music(self.current)

    # efek suara (SFX)
    def sfx(self, name, pitch=1.0, delay=0.0):
        if delay > 0:
            invoke(self.sfx, name, pitch, 0.0, delay=delay)
            return
        if not self.S.sound:
            return
        p = _find(f"sfx_{name}")
        if p is None:
            return
        try:
            Audio(p, volume=SFX_VOLUME.get(name, 0.8), pitch=pitch,
                autoplay=True, auto_destroy=True, group="sfx")
        except Exception as e:
            print("[sound] gagal memutar", name, e)
