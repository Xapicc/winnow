"""Allow running the inherited surface as: python3 -m winnow.legacy

`python3 -m winnow` is the entry point, and it is what the hook commands in
data/hooks.json fall back to when the console script is not on PATH. This one
stays because an in-place upgrade over an installed Cozempic leaves hooks
naming the old module path, and because it is the shortest way to reach the
inherited CLI without `winnow.cli`'s dispatch in front of it.
"""

from winnow.legacy.cli import main

main()
