import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps
from rest_framework import serializers

BANNER_SIZE = (600, 300)  # width x height, ratio 2:1
MIN_BANNER_WIDTH = 300
MIN_BANNER_HEIGHT = 150
MAX_BANNER_MB = 3
ALLOWED_BANNER_TYPES = ('image/jpeg', 'image/png', 'image/webp')


def validate_banner_file(file):
    """Validate size, type and minimum dimensions of an uploaded banner."""
    if file.size > MAX_BANNER_MB * 1024 * 1024:
        raise serializers.ValidationError(f"Banner must be smaller than {MAX_BANNER_MB} MB")

    content_type = getattr(file, 'content_type', '')
    if content_type not in ALLOWED_BANNER_TYPES:
        raise serializers.ValidationError("Only JPG, PNG or WEBP images are allowed")

    try:
        img = Image.open(file)
        width, height = img.size
    except Exception:
        raise serializers.ValidationError("Invalid image file")
    finally:
        file.seek(0)

    if width < MIN_BANNER_WIDTH or height < MIN_BANNER_HEIGHT:
        raise serializers.ValidationError(
            f"Banner is too small. Minimum size is {MIN_BANNER_WIDTH} x {MIN_BANNER_HEIGHT} px"
        )
    return file


def process_banner(file):
    """Center-crop and resize the image to BANNER_SIZE and return a JPEG ContentFile."""
    file.seek(0)
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)

    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert('RGB')

    img = ImageOps.fit(img, BANNER_SIZE, Image.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=88, optimize=True)
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def get_banner_url(obj, request=None):
    """Absolute URL of the request banner, or None if there is no banner."""
    if not obj.banner:
        return None
    try:
        url = obj.banner.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if request else url