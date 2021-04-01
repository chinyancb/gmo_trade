import os
import sys
from pathlib import Path
import json
import websocket

app_home = str(Path(__file__).parents[1])
sys.path.append(app_home)
websocket.enableTrace(True)
ws = websocket.WebSocketApp('wss://api.coin.z.com/ws/public/v1')

def on_open(self):
    message = {
        "command": "subscribe",
        "channel": "ticker",
        "symbol": "BTC_JPY"
    }
    ws.send(json.dumps(message))

def on_message(self, message):
    print(message)
    print(json.loads(message)['last'])
    print(int(json.loads(message)['last']))

ws.on_open = on_open
ws.on_message = on_message

ws.run_forever()
