import os
import sys
from pathlib import Path
import json
import asyncio
import websockets

app_home = str(Path(__file__).parents[1])
sys.path.append(app_home)

async def main():
    url = 'wss://api.coin.z.com/ws/public/v1'
    with websockets.connect(url) as ws:
        message = {
            "command": "subscribe",
            "channel": "ticker",
            "symbol": "BTC"
        }
    ws.send(json.dumps(message))
    ws.recv()


if __name__ == '__main__':
    main()
