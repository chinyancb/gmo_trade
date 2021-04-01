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
method    = 'POST'
endPoint  = 'https://api.coin.z.com/private'
path      = '/v1/order'
reqBody = {
    "symbol": "BTC_JPY",
    "side": "BUY",
    "executionType": "LIMIT",
    "timeInForce": "FAS",
    "price": f"{sys.argv[1]}",
#    "losscutPrice": "30012",
    "size": "0.01"
}
print('---------------')
print(reqBody)
print('---------------')

text = timestamp + method + path + json.dumps(reqBody)
sign = hmac.new(bytes(secretKey.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()

headers = {
    "API-KEY": apiKey,
    "API-TIMESTAMP": timestamp,
    "API-SIGN": sign
}

res = requests.post(endPoint + path, headers=headers, data=json.dumps(reqBody))
print (json.dumps(res.json(), indent=2))
