"""Allow ``python -m kalshi_trades`` as a shortcut to the watcher CLI."""

from kalshi_trades.watcher import main
import asyncio

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nStopped.")
