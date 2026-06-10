# meta developer: @zetmodules
# meta version: 2.1
# meta description: .dn — мем "Ёбаный даун" с аватаркой юзера (GIF). Без реплая = своя аватарка.

import io
import os
import asyncio
import aiohttp
import tempfile
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .. import loader, utils

BASE_IMAGE_URL = "https://raw.githubusercontent.com/ziwupa/Downed/main/base.mp4"
AVATAR_BOX = (607, 148, 1080, 581)

TG_COLORS = [
    (255, 80,  80),
    (255, 150, 0),
    (230, 185, 0),
    (50,  190, 100),
    (0,   150, 240),
    (120, 80,  230),
    (235, 90,  165),
]

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


@loader.tds
class DownedMod(loader.Module):
    """Мем «Ёбаный даун» — .dn [реплай] → GIF с аватаркой. Без реплая = твоя аватарка."""

    strings = {
        "name": "Downed",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
    }

    async def dncmd(self, message):
        """[reply] — мем с аватаркой. Без реплая = твоя."""
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

            gif_buf = await asyncio.get_event_loop().run_in_executor(
                None, self._make_gif, avatar_bytes
            )

            await message.client.send_file(
                message.chat_id,
                gif_buf,
                caption=None,
                reply_to=reply_to,
                force_document=False,
            )

        except Exception as e:
            await message.client.send_message(
                message.chat_id,
                self.strings["error"].format(str(e)),
                parse_mode="html",
            )

    async def _fetch_url(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                return await resp.read()

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
    def _make_name_avatar(name: str, uid: int) -> bytes:
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

    def _make_gif(self, avatar_bytes: bytes) -> io.BytesIO:
        base_bytes = self._get_base_frame()
        if not base_bytes:
            raise RuntimeError("Не удалось загрузить базу")

        base = Image.open(io.BytesIO(base_bytes)).convert("RGB")
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")

        left, top, right, bottom = AVATAR_BOX
        box_w = right - left
        box_h = bottom - top

        avatar_img = avatar_img.resize((box_w, box_h), Image.LANCZOS)
        avatar_img = self._jpeg_shakalize(avatar_img, quality=8)
        base.paste(avatar_img, (left, top))
        base = self._jpeg_shakalize(base, quality=8)

        frame = base.quantize(colors=128, method=Image.Quantize.FASTOCTREE)

        buf = io.BytesIO()
        buf.name = "downed.gif"
        frame.save(
            buf,
            format="GIF",
            save_all=True,
            append_images=[],
            optimize=False,
            duration=100,
            loop=0,
        )
        buf.seek(0)
        return buf

    @staticmethod
    def _fetch_sync(url: str) -> bytes | None:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception:
            return None

    def _get_base_frame(self) -> bytes | None:
        """Скачивает MP4 и извлекает первый кадр как JPEG."""
        import subprocess
        import tempfile
        video_bytes = self._fetch_sync(BASE_IMAGE_URL)
        if not video_bytes:
            return None
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            vf.write(video_bytes)
            video_path = vf.name
        out_path = tempfile.mktemp(suffix=".jpg")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vframes", "1", "-q:v", "2",
                out_path
            ], check=True, timeout=15,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(out_path, "rb") as f:
                return f.read()
        except Exception:
            return None
        finally:
            for p in (video_path, out_path):
                try: os.unlink(p)
                except: pass
