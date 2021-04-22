#!/bin/zsh
for pid in `ps | grep -i chrome | awk '{print $1}'`
do
        kill -9 $pid
done
exit 1
