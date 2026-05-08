#!/bin/bash

rm -rf build dist

echo "_version = '$(git describe --tags --always)'" >adeversion.py
#pyinstaller --optimize 2 --windowed ade.py --icon=../resources/MyIcon.icns
pyinstaller ade.spec
#pyinstaller --optimize 2 --windowed adv.py --icon=../resources/MyIcon.icns --hidden-import='PIL._tkinter_finder'
pyinstaller adv.spec
