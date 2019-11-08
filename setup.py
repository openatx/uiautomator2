#!/usr/bin/env python
# coding: utf-8
#
# Licensed under MIT
#

import setuptools

name = 'uiautomator2'
author = 'codeskyblue'
author_email = 'codeskyblue@gmail.com'
description = 'Python Wrapper for Google Android UiAutomator2 test tool'
url = 'https://github.com/openatx/uiautomator2'
classifiers = ['Development Status :: 4 - Beta',
               'Environment :: Console',
               'Intended Audience :: Developers',
               'Operating System :: POSIX',
               'Programming Language :: Python :: 3',
               'License :: OSI Approved :: MIT License'
               'Topic :: Software Development :: Libraries :: Python Modules',
               'Topic :: Software Development :: Testing']

python_requires = '>=3.6'
version = '1.3.7'

# Read requirements from requirement file
install_requires = []
with open('requirements.txt') as f:
    for line in f.readlines():
        install_requires.append(line.rstrip())
packages = setuptools.find_packages()
entry_points = {'console_scripts': ['uiautomator2 = uiautomator2.__main__:main']}

setuptools.setup(name=name,
                 author=author,
                 author_email=author_email,
                 description=description,
                 url=url,
                 classifiers=classifiers,
                 packages=packages,
                 entry_points=entry_points,
                 install_requires=install_requires,
                 version=version,
                 python_requires=python_requires)
