#!/usr/bin/env python3
"""
Packaging for Commodore
"""
from setuptools import setup, find_packages

import commodore as package


def read_file(filename):
    """Fetch the contents of a file"""
    with open(filename) as file:
        return file.read()


setup(
    name=package.__name__,
    version=package.__version__,
    description=package.__doc__.strip().split('\n')[0],
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    url=package.__url__,
    author=package.__author__,
    author_email=package.__email__,
    license=package.__license__,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Networking',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    python_requires='>=3.6',
    packages=find_packages(exclude=['tests']),
    install_requires=read_file('requirements.in'),
    entry_points={
        'console_scripts': [
            'commodore = commodore.cli:main',
        ],
    },
)
