pip3 install readme_renderer twine
# python3 setup.py check -r -s

if [ $? -ne 0 ]; then
    echo 'fix README'
    exit
fi

rm -rf ./dist
python3 setup.py sdist
python3 setup.py bdist_wheel
twine check dist/*
twine upload dist/*