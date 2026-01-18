# firmware/effects/palette.py
import math

def clamp8(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))

def hsv_to_rgb(h, s, v):
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    if i == 0: r,g,b = v,t,p
    elif i == 1: r,g,b = q,v,p
    elif i == 2: r,g,b = p,v,t
    elif i == 3: r,g,b = p,q,v
    elif i == 4: r,g,b = t,p,v
    else: r,g,b = v,p,q
    return (clamp8(r*255), clamp8(g*255), clamp8(b*255))

def _scale(rgb, k):
    return (clamp8(rgb[0]*k), clamp8(rgb[1]*k), clamp8(rgb[2]*k))

# 7 kolorów (hue) – stałe, przyjemne przejścia
PALETTE7 = (0.00, 0.07, 0.14, 0.33, 0.50, 0.66, 0.83)

def color_for(v, t, mode="auto", power=0.85):
    """
    v: 0..1 (intensywność logiczna, NIE musi oznaczać jasności 1:1)
    t: czas (sekundy)
    mode:
      - "mono"    -> szarość
      - "rainbow" -> pełna tęcza (ale limitowana)
      - "auto"    -> spokojny hue zależny od czasu i v
      - "p7"      -> 7-kolorowa paleta (v wybiera slot, t może delikatnie pływać)
    power: 0..1 globalny limiter mocy (Twoja filozofia)
    """
    v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else float(v))
    power = 0.0 if power < 0.0 else (1.0 if power > 1.0 else float(power))

    if mode == "mono":
        c = clamp8((40 + 215*v) * power)
        return (c, c, c)

    if mode == "p7":
        k = int(round(v * 6.0))
        k = 0 if k < 0 else (6 if k > 6 else k)
        # delikatne pływanie hue w czasie, ale małe (nie dyskoteka)
        h = (PALETTE7[k] + 0.02 * math.sin(0.7 * t)) % 1.0
        # jasność minimalna, żeby nie gasło + limiter power
        rgb = hsv_to_rgb(h=h, s=1.0, v=max(0.12, v))
        return _scale(rgb, power)

    if mode == "rainbow":
        rgb = hsv_to_rgb(h=v, s=1.0, v=max(0.12, v))
        return _scale(rgb, power)

    # auto: spokojne, nielosowe, bez skoków
    h = (0.15 + 0.55*v + 0.06*t) % 1.0
    rgb = hsv_to_rgb(h=h, s=1.0, v=max(0.10, v))
    return _scale(rgb, power)
