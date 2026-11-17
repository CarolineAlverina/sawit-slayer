import wave
from pathlib import Path

import numpy as np

SR = 22050
OUT = Path(__file__).resolve().parent.parent / "audio"
RNG = np.random.default_rng(7)


def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def sine(f, dur):
    return np.sin(2 * np.pi * f * t_axis(dur))


def square(f, dur, duty=0.5):
    ph = (f * t_axis(dur)) % 1.0
    return np.where(ph < duty, 1.0, -1.0)


def tri(f, dur):
    ph = (f * t_axis(dur)) % 1.0
    return 4 * np.abs(ph - 0.5) - 1


def noise(dur):
    return RNG.uniform(-1, 1, int(SR * dur))


def sweep(f0, f1, dur, wave_fn="sine"):
    """Nada yang meluncur dari f0 ke f1."""
    t = t_axis(dur)
    f = f0 + (f1 - f0) * (t / dur)
    ph = np.cumsum(f) / SR
    if wave_fn == "square":
        return np.where(ph % 1.0 < 0.5, 1.0, -1.0)
    return np.sin(2 * np.pi * ph)


def env(n, attack=0.005, decay=None):
    """Envelope: naik cepat lalu turun eksponensial."""
    t = np.arange(n) / SR
    dur = n / SR
    decay = decay if decay is not None else dur / 4
    e = np.exp(-t / decay)
    a = min(int(SR * attack), n)
    if a > 0:
        e[:a] *= np.linspace(0, 1, a)
    return e


def lowpass(x, k):
    """Low-pass sederhana (moving average) untuk meredam noise."""
    k = max(1, int(k))
    return np.convolve(x, np.ones(k) / k, mode="same")


def fade_out(x, secs=0.02):
    n = min(len(x), int(SR * secs))
    x = x.copy()
    x[-n:] *= np.linspace(1, 0, n)
    return x


def note(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def save(name, x, peak=0.85):
    OUT.mkdir(exist_ok=True)
    x = np.asarray(x, dtype=np.float64)
    m = np.max(np.abs(x))
    if m > 0:
        x = x / m * peak
    pcm = (x * 32767).astype(np.int16)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"  {name}.wav  {len(x) / SR:.2f} dtk")


def seq(parts, gap=0.0):
    """Sambung beberapa potongan suara berurutan."""
    out = []
    for p in parts:
        out.append(p)
        if gap:
            out.append(np.zeros(int(SR * gap)))
    return np.concatenate(out)


def mix(*tracks):
    n = max(len(t) for t in tracks)
    out = np.zeros(n)
    for t in tracks:
        out[:len(t)] += t
    return out


def sfx_click():
    d = 0.07
    return fade_out(square(880, d) * env(int(SR * d), decay=0.03))


def sfx_start():
    parts = [square(note(m), 0.09) * env(int(SR * 0.09), decay=0.05)
             for m in (60, 64, 67, 72)]
    return fade_out(seq(parts))


def sfx_slash():
    """Tebasan pedang: noise dengan filter yang menyempit (whoosh) + desing."""
    d = 0.28
    n = int(SR * d)
    whoosh = noise(d)
    whoosh = lowpass(whoosh, 3) - lowpass(whoosh, 40)
    whoosh *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    ping = sweep(2400, 900, d) * env(n, decay=0.06) * 0.25
    return fade_out(whoosh * 1.4 + ping)


def sfx_palm():
    """Pohon tumbang: gedebuk rendah + ranting patah."""
    d = 0.55
    n = int(SR * d)
    thud = sweep(130, 45, d) * env(n, attack=0.01, decay=0.12)
    crack = lowpass(noise(d), 6) * env(n, attack=0.002, decay=0.05) * 0.7
    leaves = lowpass(noise(d), 18) * env(n, attack=0.15, decay=0.18) * 0.35
    return fade_out(thud * 1.2 + crack + leaves)


def sfx_water():
    """Ambil air: gelembung yang naik nadanya + kilau."""
    parts = []
    for f0 in (400, 520, 660, 840):
        d = 0.09
        parts.append(sweep(f0, f0 * 1.6, d) * env(int(SR * d), decay=0.04))
    sparkle = square(note(84), 0.2) * env(int(SR * 0.2), decay=0.09) * 0.4
    return fade_out(np.concatenate(parts + [sparkle]))


def sfx_extinguish():
    """Monster padam: desis uap + nada turun."""
    d = 0.7
    n = int(SR * d)
    hiss = lowpass(noise(d), 2) * env(n, attack=0.01, decay=0.25) * 0.8
    drop = sweep(700, 120, d, "square") * env(n, decay=0.2) * 0.35
    pop = sine(1200, 0.05) * env(int(SR * 0.05), decay=0.02)
    pop = np.pad(pop, (0, n - len(pop)))
    return fade_out(hiss + drop + pop * 0.8)


def sfx_hit():
    """Pemain kena monster: buzzer rendah turun."""
    d = 0.5
    n = int(SR * d)
    buzz = sweep(220, 70, d, "square") * env(n, decay=0.25)
    rumble = lowpass(noise(d), 10) * env(n, decay=0.15) * 0.5
    return fade_out(buzz * 0.8 + rumble)


def sfx_win():
    parts = [square(note(m), 0.14) * env(int(SR * 0.14), decay=0.09)
             for m in (60, 64, 67, 72, 67, 72)]
    parts.append(mix(*[tri(note(m), 0.9) * env(int(SR * 0.9), decay=0.5)
                       for m in (60, 64, 67, 72)]))
    return fade_out(np.concatenate(parts), 0.05)


def sfx_lose():
    parts = [square(note(m), 0.22) * env(int(SR * 0.22), decay=0.14)
             for m in (67, 63, 60)]
    parts.append(sweep(note(55), note(43), 0.9, "square")
                 * env(int(SR * 0.9), decay=0.5))
    return fade_out(np.concatenate(parts), 0.05)


def sfx_info():
    """Papan info muncul: dua nada lembut."""
    parts = [tri(note(m), 0.16) * env(int(SR * 0.16), decay=0.1)
             for m in (76, 81)]
    return fade_out(np.concatenate(parts))


BPM = 128
BEAT = 60 / BPM
BAR = 4 * BEAT


def render_music(chords, bass_roots, melody, lead_wave="square", bass_oct=-24,
                 drums=True, lead_vol=0.30, arp=True):
    """Susun musik per birama.

    chords      : daftar akor (tiga nada MIDI) per birama
    bass_roots  : nada dasar bass per birama
    melody      : daftar (offset_ketukan, midi, panjang_ketukan) per birama
    """
    total = BAR * len(chords)
    n = int(SR * total)
    out = np.zeros(n)

    def put(x, start_sec):
        i = int(start_sec * SR)
        j = min(n, i + len(x))
        if j > i:
            out[i:j] += x[:j - i]

    for bi, (chord, root, mel) in enumerate(zip(chords, bass_roots, melody)):
        t0 = bi * BAR

        for k in range(8):
            d = BEAT / 2
            x = tri(note(root + bass_oct), d) * env(int(SR * d), decay=0.2)
            put(x * 0.55, t0 + k * d)
        if arp:
            for k in range(8):
                d = BEAT / 2
                m = chord[k % 3] + 12
                x = square(note(m), d, 0.25) * env(int(SR * d), decay=0.08)
                put(x * 0.12, t0 + k * d)

        for off, m, ln in mel:
            if m is None:
                continue
            d = ln * BEAT
            gen = square if lead_wave == "square" else tri
            x = gen(note(m), d) * env(int(SR * d), attack=0.01, decay=d * 0.6)
            put(fade_out(x, 0.01) * lead_vol, t0 + off * BEAT)

        if drums:
            for k in range(4):
                d = 0.14
                kick = sweep(140, 45, d) * env(int(SR * d), decay=0.05)
                put(kick * 0.8, t0 + k * BEAT)
            for k in range(8):
                d = 0.04
                hat = (lowpass(noise(d), 1) - lowpass(noise(d), 4)) * \
                    env(int(SR * d), decay=0.012)
                put(hat * (0.35 if k % 2 else 0.2), t0 + k * BEAT / 2)
            for k in (1, 3):
                d = 0.16
                sn = lowpass(noise(d), 2) * env(int(SR * d), decay=0.05)
                put(sn * 0.45, t0 + k * BEAT)
    return out


def music_game():
    A, F, C, G = 57, 53, 48, 55
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)] * 2
    roots = [A, F, C, G] * 2
    m = [

        [(0, 81, 1), (1, 79, .5), (1.5, 76, .5), (2, 79, 1), (3, 76, 1)],
        [(0, 77, 1), (1, 76, .5), (1.5, 72, .5), (2, 76, 1), (3, 72, 1)],
        [(0, 76, 1), (1, 79, .5), (1.5, 76, .5), (2, 72, 1), (3, 67, 1)],
        [(0, 74, 1), (1, 76, .5), (1.5, 74, .5), (2, 71, 2)],

        [(0, 88, .5), (.5, 84, .5), (1, 81, 1), (2, 84, 1), (3, 81, 1)],
        [(0, 84, .5), (.5, 81, .5), (1, 77, 1), (2, 81, 1), (3, 77, 1)],
        [(0, 79, 1), (1, 84, .5), (1.5, 79, .5), (2, 76, 1), (3, 79, 1)],
        [(0, 74, 1), (1, 79, 1), (2, 83, 1), (3, 86, 1)],
    ]
    return render_music(chords, roots, m)


def music_menu():
    global BPM, BEAT, BAR
    old = BPM, BEAT, BAR
    BPM = 92
    BEAT = 60 / BPM
    BAR = 4 * BEAT
    try:
        chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)] * 2
        roots = [57, 53, 48, 55] * 2
        m = [
            [(0, 76, 2), (2, 79, 2)],
            [(0, 77, 2), (2, 81, 2)],
            [(0, 79, 2), (2, 76, 1), (3, 72, 1)],
            [(0, 74, 3), (3, None, 1)],
            [(0, 81, 2), (2, 79, 2)],
            [(0, 77, 2), (2, 76, 2)],
            [(0, 72, 2), (2, 76, 1), (3, 79, 1)],
            [(0, 74, 4)],
        ]
        return render_music(chords, roots, m, lead_wave="tri", drums=False,
                            lead_vol=0.45)
    finally:
        BPM, BEAT, BAR = old


def loop_safe(x):
    n = int(SR * 0.01)
    x = x.copy()
    x[:n] *= np.linspace(0, 1, n)
    x[-n:] *= np.linspace(1, 0, n)
    return x


if __name__ == "__main__":
    print("Membuat efek suara ->", OUT)
    save("sfx_click", sfx_click())
    save("sfx_start", sfx_start())
    save("sfx_slash", sfx_slash())
    save("sfx_palm", sfx_palm())
    save("sfx_water", sfx_water())
    save("sfx_extinguish", sfx_extinguish())
    save("sfx_hit", sfx_hit())
    save("sfx_info", sfx_info())
    save("sfx_win", sfx_win())
    save("sfx_lose", sfx_lose())
    print("Membuat musik")
    save("music_menu", loop_safe(music_menu()), peak=0.7)
    save("music_game", loop_safe(music_game()), peak=0.7)
    print("Selesai.")
