import sys
import requests
import json
import hmac
import hashlib
import time
from datetime import datetime

apiKey    = '6QReB6O4QiNrQQwW9xlOAMTiPTfoDbzg'
secretKey = '3HwyiibyeEqXa2MzTmhJrI4VRUm4QAiA82zt3DEOLRmNhgWwN0DiNvS4ayA5I+hT'

timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
method    = 'GET'
endPoint  = 'https://api.coin.z.com/private'
path      = '/v1/openPositions'

text = timestamp + method + path
sign = hmac.new(bytes(secretKey.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()
parameters = {
    "symbol": "BTC_JPY",
    "page": 1,
    "count": 100
}

headers = {
    "API-KEY": apiKey,
    "API-TIMESTAMP": timestamp,
    "API-SIGN": sign
}

res = requests.get(endPoint + path, headers=headers, params=parameters)
print (json.dumps(res.json(), indent=2))
