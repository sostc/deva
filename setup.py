from setuptools import setup, find_packages
from os.path import exists

setup(
    name='deva',
    version='3.0.0',
    include_package_data=True,
    packages=find_packages(),
    python_requires='>=3.8',
    author='spark',
    author_email='zjw0358@gmail.com',
    url='https://github.com/sostc/deva',
    license='http://www.apache.org/licenses/LICENSE-2.0.html',
    description='智能数据处理平台 - Intelligent data processing platform with streaming and AI capabilities',
    long_description=(open('README_PYPI.rst').read() if exists('README_PYPI.rst')
                      else open('README.rst').read() if exists('README.rst')
                      else ''),
    long_description_content_type='text/x-rst',
    install_requires=[
        # Core
        'tornado>=6.0',
        'pandas>=1.0',
        'dill>=0.3',
        'toolz>=0.10',

        # AI/LLM
        'openai>=1.0.0',

        # Search and text processing
        'whoosh>=2.7',
        'jieba>=0.39',

        # Web framework and UI
        'pywebio>=1.8',
        'pywebio-battery>=0.2',

        # Database and storage
        'sqlalchemy>=2.0',
        'walrus>=0.3',

        # Scheduling
        'apscheduler>=3.9',

        # HTTP and networking
        'requests>=2.28',
        'requests-html>=0.10',
        'aiohttp>=3.8',

        # Data analysis
        'akshare>=1.0',

        # Utilities
        'pymaybe',
        'pampy>=0.3',
        'expiringdict>=1.2',

        # Newspaper and content extraction
        'newspaper3k>=0.2',

        # WebSocket
        'sockjs-tornado>=1.0',

        # WSGI utilities
        'Werkzeug>=2.0',
    ],
    extras_require={
        'dev': [
            'IPython>=8.0',
            'pytest>=7.0',
            'twine>=4.0',
            'readme_renderer',
        ],
    },
    zip_safe=False

)
