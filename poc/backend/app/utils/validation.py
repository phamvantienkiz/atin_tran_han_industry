import re

from app.exceptions.custom import ValidationError

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_safe_name(name: str) -> str:
    """Validate filenames/folder names against path traversal and unsafe characters."""
    if not name or not SAFE_NAME_RE.match(name) or ".." in name:
        raise ValidationError("Tên tệp hoặc thư mục không hợp lệ")
    return name
