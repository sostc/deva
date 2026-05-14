"""Deva 安装配置"""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent.resolve()

long_description = (here / "README.md").read_text(encoding="utf-8") if (here / "README.md").exists() else ""

setup(
    name="deva",
    version="1.8.0",
    description="智能数据处理平台",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Deva Team",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    install_requires=[
        "pywebio>=1.8.0",
        "tornado>=6.0",
        "sqlitedict>=2.1.0",
        "aiohttp>=3.8.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
    ],
    entry_points={
        "console_scripts": [
            "naja=deva.naja.__main__:main",
        ],
    },
    include_package_data=True,
    package_data={
        "deva": [
            "naja/config/**/*",
            "naja/dictionary/**/*",
        ],
    },
)
