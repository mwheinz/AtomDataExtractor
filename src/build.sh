#!/bin/bash

rm -rf build dist ade.spec

echo "_version = '$(git describe --tags --always)'" >adeversion.py
pyinstaller --windowed ade.py --icon=../resources/MyIcon.icns
pyinstaller --windowed adv.py --icon=../resources/MyIcon.icns
