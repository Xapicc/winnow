"""Allow running the inherited surface as: python3 -m winnow.legacy

`python3 -m winnow` is the entry point; this one stays because the hook
commands in data/hooks.json fall back to it when the console script is not on
PATH, and because it is what an in-place upgrade leaves behind.
"""

from winnow.legacy.cli import main

main()
