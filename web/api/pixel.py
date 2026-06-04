"""GET /api/pixel?id=<uuid> → records open, returns 1x1 GIF."""
import os
import sys

# Re-use the existing battle-tested pixel implementation.
_here = os.path.dirname(__file__)
_pixel = os.path.abspath(os.path.join(_here, "..", "..", "vercel-pixel", "api"))
if _pixel not in sys.path:
    sys.path.insert(0, _pixel)

from pixel import handler  # noqa: F401  (re-exported as Vercel entrypoint)
