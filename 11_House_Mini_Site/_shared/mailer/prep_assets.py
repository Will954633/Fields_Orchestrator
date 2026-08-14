import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image
import os

SRC = "/home/fields/Fields_Orchestrator/11_House_Mini_Site/tab_shots"
OUT = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(OUT, exist_ok=True)

GREEN = (34, 56, 44)      # #22382c
TERRA = (183, 103, 73)    # #b76749
PAPER = (253, 243, 236)   # #fdf3ec

def crop(name, box, out):
    im = Image.open(os.path.join(SRC, name)).convert("RGB")
    im.crop(box).save(os.path.join(OUT, out))
    print("cropped", out, im.crop(box).size)

# hero.png and val_method.png are now captured LIVE from the current report design
# via capture_report_shots.js (25-huntingdale-crescent-robina) — do NOT regenerate
# them from the stale June tab_shots here.
# Named comparables table
crop("valuation__slice_02.png", (0, 150, 1366, 895), "val_comps.png")
# Three buyer personas
crop("buyers__slice_02.png", (0, 38, 1366, 706), "buyers.png")
# Satellite parcel
crop("home__slice_03.png", (0, 48, 1366, 900), "satellite.png")
# Buyers headline stat tiles (narrower pool)
crop("buyers__slice_01.png", (0, 108, 1366, 520), "buyers_stats.png")

# ---- QR code ----
url = "https://fieldsestate.com.au/analyse-your-home?utm_source=mailer&utm_medium=print&utm_campaign=home_report"
qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=2)
qr.add_data(url)
qr.make(fit=True)
img = qr.make_image(image_factory=StyledPilImage,
                    module_drawer=RoundedModuleDrawer(),
                    color_mask=SolidFillColorMask(back_color=PAPER, front_color=GREEN))
img.save(os.path.join(OUT, "qr.png"))
print("QR saved ->", url)
print("QR size", img.size)
