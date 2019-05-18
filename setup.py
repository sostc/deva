from setuptools import setup, find_packages
from os.path import exists

setup(
    name='deva',
    version=0.2,
    packages=find_packages(),
    author='spark',
    author_email='zjw0358@gmail.com',
    url='https://github.com/sostc/deva',
    license='http://www.apache.org/licenses/LICENSE-2.0.html',
    description='data eval in future',
    long_description=(open('README.rst').read() if exists('README.rst')
                        else ''),
    install_requires=list(open('requirements.txt').read().strip().split('\n')),
    zip_safe=False

)
