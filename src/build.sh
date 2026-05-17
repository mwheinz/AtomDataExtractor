#!/bin/bash

rm -rf build dist

echo "_version = '$(git describe --tags --always)'" >advversion.py
#pyinstaller --optimize 2 --windowed adv.py --icon=../resources/MyIcon.icns --hidden-import='PIL._tkinter_finder'
pyinstaller adv.spec
