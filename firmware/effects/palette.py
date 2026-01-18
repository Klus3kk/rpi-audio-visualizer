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

def scale_rgb(c, k):
    k = 0.0 if k < 0.0 else (1.0 if k > 1.0 else float(k))
    return (clamp8(c[0]*k), clamp8(c[1]*k), clamp8(c[2]*k))

def color_for(v, t, mode="auto", power=0.70):
    """
    power: globalny limiter mocy (0.45..0.85)
    """
    v = max(0.0, min(1.0, float(v)))

    if mode == "mono":
        c = clamp8(30 + 160*v)     # mniej jasno
        return scale_rgb((c, c, c), power)

    if mode == "rainbow":
        c = hsv_to_rgb(h=v, s=1.0, v=max(0.08, 0.35*v))  # dużo mniej jasno
        return scale_rgb(c, power)

    # auto
    h = (0.15 + 0.55*v + 0.06*t) % 1.0
    c = hsv_to_rgb(h=h, s=1.0, v=max(0.06, 0.32*v))
    return scale_rgb(c, power)
