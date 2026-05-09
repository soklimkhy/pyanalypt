import os
from django.core.exceptions import ValidationError

# Magic byte signatures for binary formats that can be spoofed by renaming.
# XLSX is a ZIP-based format; Parquet has a fixed 4-byte header.
_MAGIC_BYTES: dict[str, bytes] = {
    ".xlsx": b"PK\x03\x04",
    ".parquet": b"PAR1",
}


def validate_file_size_and_type(value):
    """
    Validation for datasets:
    - Size limit: 25MB
    - Formats: CSV, XLSX, JSON, Parquet
    - Binary formats (xlsx, parquet) are verified against their magic bytes
      so a renamed file cannot bypass the extension check.
    """
    # 25MB Limit
    filesize = value.size
    if filesize > 25 * 1024 * 1024:
        raise ValidationError("The maximum file size that can be uploaded is 25MB")

    # Extension Check
    ext = os.path.splitext(value.name)[1].lower()
    valid_extensions = [".csv", ".xlsx", ".json", ".parquet"]
    if ext not in valid_extensions:
        raise ValidationError("Unsupported file extension. Use CSV, XLSX, JSON, or Parquet.")

    # Magic bytes check for binary formats
    expected_magic = _MAGIC_BYTES.get(ext)
    if expected_magic:
        value.seek(0)
        header = value.read(len(expected_magic))
        value.seek(0)
        if header != expected_magic:
            raise ValidationError(
                f"File content does not match the declared {ext} format."
            )
