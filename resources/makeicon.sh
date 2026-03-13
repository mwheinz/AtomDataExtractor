#!/bin/zsh

mkdir -p MyIcon.iconset
for i in 64 128 256 512; do
    sips -z $i $i icon.png --out MyIcon.iconset/icon_${i}x${i}.png
done
iconutil -c icns MyIcon.iconset

rm -rf MyIcon.iconset
