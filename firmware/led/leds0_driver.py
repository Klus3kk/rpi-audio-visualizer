# import os
# import threading

# class Leds0Driver:
#     def __init__(self, num_leds=256, device="/dev/leds0"):
#         self.num_leds = num_leds
#         self.device = device
#         self.buf = bytearray(num_leds * 3)  # RGB
#         self.lock = threading.Lock()

#         if not os.path.exists(self.device):
#             raise RuntimeError(f"{self.device} not found (ws2812-pio overlay?)")

#         self.fd = os.open(self.device, os.O_WRONLY)

#     def set_pixel(self, i, rgb):
#         if i < 0 or i >= self.num_leds:
#             return
#         r, g, b = rgb
#         with self.lock:
#             self.buf[i*3:(i+1)*3] = bytes((r, g, b))

#     def fill(self, rgb):
#         r, g, b = rgb
#         with self.lock:
#             for i in range(self.num_leds):
#                 self.buf[i*3:(i+1)*3] = bytes((r, g, b))

#     def show(self):
#         with self.lock:
#             os.write(self.fd, self.buf)

#     def clear(self):
#         self.fill((0, 0, 0))
#         self.show()

#     def close(self):
#         os.close(self.fd)
