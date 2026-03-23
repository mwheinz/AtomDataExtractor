#!/bin/bash

rm -rf build dist ade.spec

echo "_version = '$(git describe --tags --always)'" >adeversion.py
pyinstaller --optimize 2 --windowed ade.py --icon=../resources/MyIcon.icns
pyinstaller --optimize 2 --windowed adv.py --icon=../resources/MyIcon.icns --hidden-import='PIL._tkinter_finder'
