#!/usr/bin/env bash

# For more information consult https://packaging.python.org/tutorials/packaging-projects

# Make sure that only the newest distribution will be uploaded
rm -rf dist
# Make sure you have the latest versions of setuptools and wheel installed:
python3 -m pip install --user --upgrade setuptools wheel
# Now run this command from the same directory where setup.py is located:
python3 setup.py sdist bdist_wheel

# Now that you are registered, you can use twine to upload the distribution packages. You’ll need to install Twine:
python3 -m pip install --user --upgrade twine

# Once installed, run Twine to upload all of the archives under dist:
# This will upload to the pypi site, if you want to use the test pypi you should run:
# python3 -m twine upload --repository testpypi dist/*
python3 -m twine upload dist/*
