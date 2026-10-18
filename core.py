"""Conversion and image operations. Originals are never overwritten."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.gif'}
MEDIA = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.mp3', '.wav', '.flac', '.ogg', '.m4a'}
DOCUMENTS = {'.doc', '.docx', '.odt', '.rtf', '.ppt', '.pptx', '.odp', '.xls', '.xlsx', '.ods'}


def targets(path):
    suffix = Path(path).suffix.lower()
    if suffix in IMAGES:
        return ['PNG', 'JPG', 'WEBP', 'PDF', 'TIFF', 'BMP']
    if suffix == '.pdf':
        return ['PNG', 'JPG', 'TXT']
    if suffix in MEDIA:
        return ['MP4', 'WEBM', 'MP3', 'WAV', 'FLAC']
    if suffix in DOCUMENTS:
        return ['PDF']
    return []


def run(args):
    if not shutil.which(args[0]):
        packages = {'ffmpeg': 'ffmpeg', 'pdftoppm': 'poppler-utils',
                    'pdftotext': 'poppler-utils', 'libreoffice': 'libreoffice'}
        raise ValueError(f"Install {packages.get(args[0], args[0])} to use this operation.")
    result = subprocess.run(args, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or 'Conversion failed.')[-2000:])


def publish(source, original, label, suffix):
    """Exclusive creation prevents collisions, including concurrent jobs."""
    original = Path(original)
    for index in range(10000):
        extra = f' ({index})' if index else ''
        output = original.with_name(f'{original.stem}{label}{extra}.{suffix.lower()}')
        try:
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, 'wb') as dest, open(source, 'rb') as src:
                shutil.copyfileobj(src, dest)
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        return output
    raise ValueError('Too many files with the same output name.')


def load_image(path):
    with Image.open(path) as im:
        im.seek(0)
        return ImageOps.exif_transpose(im).convert('RGBA')


def opaque(image):
    bg = Image.new('RGB', image.size, 'white')
    rgba = image.convert('RGBA')
    bg.paste(rgba, mask=rgba.getchannel('A'))
    return bg


def save_image(image, path, label=' Edited', fmt='PNG', quality=85):
    fmt = fmt.upper()
    fmt = 'JPEG' if fmt == 'JPG' else fmt
    with tempfile.TemporaryDirectory(prefix='dragvert-') as tmp:
        output = Path(tmp) / 'output'
        im = opaque(image) if fmt in {'JPEG', 'PDF', 'BMP'} else image
        # Deliberately strip source metadata from new exports.
        im = im.copy()
        im.info.clear()
        im.save(output, format=fmt, quality=quality, optimize=True)
        return publish(output, path, label, 'jpg' if fmt == 'JPEG' else fmt)


def convert(path, target, quality=85):
    path = Path(path).resolve(strict=True)
    target = target.upper()
    if not path.is_file() or target not in targets(path):
        raise ValueError(f'Unsupported conversion: {path.name} → {target}')
    suffix = path.suffix.lower()
    if suffix in IMAGES:
        return [save_image(load_image(path), path, '', target, quality)]
    with tempfile.TemporaryDirectory(prefix='dragvert-') as tmp:
        tmp = Path(tmp)
        out = tmp / ('converted.' + target.lower())
        if suffix == '.pdf':
            if target == 'TXT':
                run(['pdftotext', '-layout', str(path), str(out)])
            else:
                prefix = tmp / 'page'
                run(['pdftoppm', '-r', '150', '-png' if target == 'PNG' else '-jpeg', str(path), str(prefix)])
                pages = sorted(tmp.glob('page-*'), key=lambda p: int(p.stem.split('-')[-1]))
                if not pages:
                    raise ValueError('The PDF produced no pages.')
                return [publish(p, path, f' Page {i:03}', target) for i, p in enumerate(pages, 1)]
        elif suffix in MEDIA:
            options = {
                'MP4': ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:a', 'aac', '-movflags', '+faststart'],
                'WEBM': ['-c:v', 'libvpx-vp9', '-c:a', 'libopus'],
                'MP3': ['-vn', '-c:a', 'libmp3lame', '-q:a', '2'],
                'WAV': ['-vn', '-c:a', 'pcm_s16le'],
                'FLAC': ['-vn', '-c:a', 'flac'],
            }
            run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), *options[target], str(out)])
        else:
            profile = (tmp / 'profile').as_uri()
            run(['libreoffice', f'-env:UserInstallation={profile}', '--headless', '--convert-to', 'pdf', '--outdir', str(tmp), str(path)])
            out = tmp / (path.stem + '.pdf')
        if not out.is_file() or not out.stat().st_size:
            raise ValueError('The converter did not produce an output file.')
        return [publish(out, path, '', target)]


def compress(path, quality=75):
    path = Path(path)
    if path.suffix.lower() not in IMAGES:
        raise ValueError('Compression currently supports still images. Convert other files first.')
    fmt = 'WEBP' if path.suffix.lower() == '.webp' else 'JPG'
    return [save_image(load_image(path), path, ' Compressed', fmt, quality)]


def metadata(path):
    path = Path(path)
    data = {'Name': path.name, 'Location': str(path.parent), 'Bytes': path.stat().st_size}
    if path.suffix.lower() in IMAGES:
        with Image.open(path) as im:
            data.update(Format=im.format, Width=im.width, Height=im.height,
                        Mode=im.mode, Frames=getattr(im, 'n_frames', 1))
            from PIL.ExifTags import TAGS
            data['EXIF'] = {TAGS.get(k, str(k)): str(v)[:500] for k, v in im.getexif().items()}
    return json.dumps(data, indent=2, ensure_ascii=False)


def crop_image(image, box):
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.width, x2), min(image.height, y2)
    if x2 <= x1 or y2 <= y1:
        raise ValueError('Draw a crop rectangle on the image first.')
    return image.crop((x1, y1, x2, y2))


def redact_image(image, box):
    result = image.copy()
    ImageDraw.Draw(result).rectangle(box, fill=(0, 0, 0, 255))
    return result


def annotate_image(image, text, xy, size=32, color='#ffffff'):
    result = image.copy()
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, size) if Path(font_path).exists() else ImageFont.load_default()
    ImageDraw.Draw(result).text(xy, text, font=font, fill=color, stroke_width=max(1, size // 16), stroke_fill='#17212e')
    return result


def background(image, padding=80, radius=24, shadow=24, colors=('#ffb35c', '#7061e8')):
    from PIL import ImageColor
    padding, radius, shadow = int(padding), int(radius), int(shadow)
    w, h = image.width + 2 * padding, image.height + 2 * padding
    a, b = ImageColor.getrgb(colors[0]), ImageColor.getrgb(colors[1])
    ramp = Image.new('RGB', (1, h))
    ramp.putdata([tuple(round(a[k] + (b[k] - a[k]) * y / max(1, h - 1)) for k in range(3)) for y in range(h)])
    canvas = ramp.resize((w, h)).convert('RGBA')
    mask = Image.new('L', image.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    from PIL import ImageChops
    mask = ImageChops.multiply(mask, image.getchannel('A'))
    if shadow:
        shadow_mask = Image.new('L', (w, h))
        shadow_mask.paste(mask, (padding, padding + shadow // 3))
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda x: x // 2)
        shade = Image.new('RGBA', (w, h), 'black')
        shade.putalpha(shadow_mask)
        canvas = Image.alpha_composite(canvas, shade)
    canvas.paste(image, (padding, padding), mask)
    return canvas
