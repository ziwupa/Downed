# meta developer: @zetmodules
# meta version: 3.0
# meta description: .dn — мем "Ёбаный даун" с аватаркой (MP4-гифка). Без реплая = своя аватарка.

import io
import os
import asyncio
import tempfile
import subprocess

from PIL import Image, ImageDraw, ImageFont
from telethon.tl.types import User

from .. import loader, utils

BASE_VIDEO_URL = "https://raw.githubusercontent.com/ziwupa/Downed/main/base.mp4"

# Координаты зоны под аватарку (для видео 848x464)
AVATAR_BOX = (480, 120, 848, 464)

# Точные цвета Telegram (user_id % 7)
TG_COLORS = [
    (255, 80,  80),    # 0 — красный
    (255, 150, 0),     # 1 — оранжевый
    (230, 185, 0),     # 2 — жёлтый
    (50,  190, 100),   # 3 — зелёный
    (0,   150, 240),   # 4 — синий
    (120, 80,  230),   # 5 — фиолетовый
    (235, 90,  165),   # 6 — розовый
]

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


@loader.tds
class DownedMod(loader.Module):
    """Мем «Ёбаный даун» — .dn реплай на юзера → его аватарка на место unsido (MP4-гифка)"""

    strings = {
        "name": "Downed",
        "no_reply": "❌ <b>Ответь на сообщение</b>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
    }

    async def dncmd(self, message):
        """[reply] — мем с аватаркой. Без реплая = твоя аватарка."""
        reply = await message.get_reply_message()

        if reply:
            sender = await reply.get_sender()
            reply_to = reply.id
            is_self = False
        else:
            sender = await message.get_sender()
            reply_to = None
            is_self = True

        try:
            await message.delete()

            avatar_bytes = await self._get_avatar(message.client, sender, is_self=is_self)

            if sender:
                first = getattr(sender, "first_name", "") or ""
                last  = getattr(sender, "last_name",  "") or ""
                name  = (first + " " + last).strip() or getattr(sender, "username", None) or "??"
                uid   = getattr(sender, "id", 0) or 0
            else:
                name, uid = "??", 0

            if not avatar_bytes:
                avatar_bytes = self._make_name_avatar(name, uid)

            mp4_buf = await asyncio.get_event_loop().run_in_executor(
                None, self._make_mp4, avatar_bytes
            )

            await message.client.send_file(
                message.chat_id,
                mp4_buf,
                caption=None,
                reply_to=reply_to,
                force_document=False,
                supports_streaming=True,
                attributes=[],
            )

        except Exception as e:
            await message.client.send_message(
                message.chat_id,
                self.strings["error"].format(str(e)),
                parse_mode="html",
            )

    async def _get_avatar(self, client, entity, is_self: bool = False) -> bytes | None:
        try:
            buf = io.BytesIO()
            if is_self:
                me = await client.get_me()
                result = await client.download_profile_photo(me, file=buf)
            else:
                result = await client.download_profile_photo(entity, file=buf)
            if result is None:
                return None
            buf.seek(0)
            data = buf.read()
            return data if data else None
        except Exception:
            return None

    @staticmethod
    def _fetch_sync(url: str) -> bytes | None:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception:
            return None

    @staticmethod
    def _make_name_avatar(name: str, uid: int) -> bytes:
        """Цвет как в Telegram (uid % 7) + полный ник"""
        left, top, right, bottom = AVATAR_BOX
        w = right - left
        h = bottom - top

        color = TG_COLORS[uid % 7]
        img = Image.new("RGB", (w, h), color)
        draw = ImageDraw.Draw(img)

        font = None
        for path in FONT_PATHS:
            try:
                font = ImageFont.truetype(path, 10)
                break
            except Exception:
                continue

        for font_size in range(120, 8, -2):
            f = font.font_variant(size=font_size) if font else ImageFont.load_default()
            bbox = draw.textbbox((0, 0), name, font=f)
            if (bbox[2] - bbox[0]) <= w - 24 and (bbox[3] - bbox[1]) <= h - 24:
                break

        bbox = draw.textbbox((0, 0), name, font=f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (w - tw) // 2 - bbox[0]
        y = (h - th) // 2 - bbox[1]
        draw.text((x, y), name, fill="white", font=f)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def _jpeg_shakalize(img: Image.Image, quality: int) -> Image.Image:
        tmp = io.BytesIO()
        img.save(tmp, format="JPEG", quality=quality)
        tmp.seek(0)
        return Image.open(tmp).convert("RGB")

    def _make_mp4(self, avatar_bytes: bytes) -> io.BytesIO:
        """
        Скачивает base.mp4, накладывает аватарку через ffmpeg overlay,
        возвращает mp4 без звука (Telegram воспринимает как гифку).
        """
        video_bytes = self._fetch_sync(BASE_VIDEO_URL)
        if not video_bytes:
            raise RuntimeError("Не удалось скачать base.mp4")

        left, top, right, bottom = AVATAR_BOX
        box_w = right - left
        box_h = bottom - top

        # Подготовим аватарку с артефактами
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        avatar_img = avatar_img.resize((box_w, box_h), Image.LANCZOS)
        avatar_img = self._jpeg_shakalize(avatar_img, quality=8)

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "base.mp4")
            avatar_path = os.path.join(tmpdir, "avatar.jpg")
            out_path = os.path.join(tmpdir, "out.mp4")

            with open(video_path, "wb") as f:
                f.write(video_bytes)

            avatar_img.save(avatar_path, format="JPEG", quality=85)

            # ffmpeg: overlay аватарки поверх видео, без звука
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", avatar_path,
                "-filter_complex",
                f"[1:v]scale={box_w}:{box_h}[ov];[0:v][ov]overlay={left}:{top}",
                "-an",           # без звука → Telegram = гифка
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                out_path
            ], check=True, timeout=60,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            with open(out_path, "rb") as f:
                data = f.read()

        buf = io.BytesIO(data)
        buf.name = "downed.mp4"
        buf.seek(0)
        return buf
