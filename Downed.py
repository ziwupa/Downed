# meta developer: @zetmodules
# meta version: 3.0
# meta description: .dn — мем "Ёбаный даун" с аватаркой юзера (MP4). Без реплая = своя аватарка.

import io
import os
import asyncio
import aiohttp
import tempfile
import subprocess

from PIL import Image, ImageDraw, ImageFont
from .. import loader, utils

BASE_VIDEO_URL = "https://files.catbox.moe/qxawqe.mp4"
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
    """Мем «Ёбаный даун» — .dn [реплай] → MP4 с аватаркой"""

    strings = {
        "name": "Downed",
        "no_reply": "❌ <b>Ответь на сообщение</b>",
        "error": "❌ <b>Ошибка:</b> <code>{}</code>",
    }

    async def dncmd(self, message):
        """[reply] — мем с аватаркой. Без реплая = твоя аватарка."""
        reply = await message.get_reply_message()
        sender = None

        if reply:
            sender = await reply.get_sender()
            reply_to = reply.id
        else:
            sender = await message.get_sender()
            reply_to = None

        try:
            await message.delete()

            avatar_bytes = await self._get_avatar(message.client, sender, is_self=(reply is None))

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
                supports_streaming=True,
            )

        except Exception as e:
            await message.client.send_message(
                message.chat_id,
                self.strings["error"].format(str(e)),
                parse_mode="html",
            )

    async def _fetch_url(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
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

        f = ImageFont.load_default()
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

    def _make_mp4(self, avatar_bytes: bytes) -> io.BytesIO:
        base_video = self._fetch_sync(BASE_VIDEO_URL)
        if not base_video:
            raise RuntimeError("Не удалось скачать видео")

        left, top, right, bottom = AVATAR_BOX
        box_w = right - left
        box_h = bottom - top

        # Временные файлы
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
            vf.write(base_video)
            video_path = vf.name

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as af:
            af.write(avatar_bytes)
            avatar_path = af.name

        out_path = tempfile.mktemp(suffix=".mp4")

        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", avatar_path,
                "-filter_complex",
                f"[1:v]scale={box_w}:{box_h}:force_original_aspect_ratio=decrease,"
                f"pad={box_w}:{box_h}:(ow-iw)/2:(oh-ih)/2:black[avt];"
                f"[0:v][avt]overlay={left}:{top}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "26",
                "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                out_path
            ], check=True, timeout=30,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            with open(out_path, "rb") as f:
                data = f.read()
            buf = io.BytesIO(data)
            buf.name = "downed.mp4"
            return buf
        finally:
            for p in (video_path, avatar_path, out_path):
                try:
                    os.unlink(p)
                except Exception:
                    pass

    @staticmethod
    def _fetch_sync(url: str) -> bytes | None:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception:
            return None
