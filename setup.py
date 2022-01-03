from os import path as p

from setuptools import find_packages, setup


def read(filename, parent=None):
    parent = parent or __file__

    try:
        with open(p.join(p.dirname(parent), filename)) as f:
            return f.read()
    except IOError:
        return ""


setup(
    name="nextion",
    version="1.8.1",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.6.0, <4",
    license="LGPL 3",
    author="Jevgeni Kiski",
    author_email="yozik04@gmail.com",
    description="Nextion display serial client",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    keywords="nextion serial async asyncio",
    url="https://github.com/yozik04/nextion",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
    install_requires=["pyserial-asyncio"],
    setup_requires=["wheel"],
    tests_require=["asynctest"],
    entry_points={
        "console_scripts": [
            "nextion-fw-upload = nextion.console_scripts.upload_firmware:main"
        ]
    },
)
