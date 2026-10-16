import asyncio
from ai_redaction import run_meta_ai_cdp_async
loop = asyncio.get_event_loop()
res = loop.run_until_complete(run_meta_ai_cdp_async("test prompt", []))
print(f"Result: {res}")
