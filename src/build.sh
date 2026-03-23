#!/bin/bash

rm -rf build dist ade.spec

echo "_version = '$(git describe --tags --always)'" >adeversion.py
pyinstaller --optimize --windowed ade.py --icon=../resources/MyIcon.icns
pyinstaller --optimize --windowed adv.py --icon=../resources/MyIcon.icns
