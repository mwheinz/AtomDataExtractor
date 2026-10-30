#!/bin/bash

rm -rf build dist

echo "_version = '$(git describe --tags --always)'" >advversion.py

pyinstaller adv.spec
