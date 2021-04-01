import numpy as np
import pandas as pd



df = pd.DataFrame(np.arange(30).reshape(10, 3), columns=['a b c'.split( )])
print(df)
print('------')

print(type(df))
print('------')

h = 10
if any(df['a'] > h):
    print('ok')
else:
    print('ng')

print('------')
print(df.a > 10)

print('------')
if any(df.a > 10):
    print('ok')
else:
    print('ng')




# データフレームで返される
print('------')
print(df['a'] > 10)

s = '-+-one-+-'
print(s)
print(s.strip('-+'))
s = '  one  '
print(s)
print(s.strip())
print('------')

df2 = df.copy()

if any(df2['a'] > h):
    print('ok')
else:
    print('ng')

print('------')
result = any(df['a'] > h)
print(f'result : [{result}]')


print('------')
print(f"{if any(df['a'] > h):pass}")
