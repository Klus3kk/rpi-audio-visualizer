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

def color_for(v, t, mode="auto"):
    v = max(0.0, min(1.0, float(v)))
    if mode == "mono":
        c = clamp8(40 + 215*v)
        return (c, c, c)
    if mode == "rainbow":
        return hsv_to_rgb(h=v, s=1.0, v=max(0.15, v))
    # auto: hue zależne od czasu i wartości
    return hsv_to_rgb(h=(0.15 + 0.55*v + 0.08*t), s=1.0, v=max(0.10, v))
