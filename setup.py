from setuptools import setup, find_packages

setup(
    name='deva',
    version=0.1,
    packages=find_packages(),
    author='spark',
    author_email='zjw0358@gmail.com',
    url='http://github.com/sostc/deva',
    license='http://www.apache.org/licenses/LICENSE-2.0.html',
    description='data eval in future',
    install_requires=["requests", "streamz"]
)
