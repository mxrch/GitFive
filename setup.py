#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

requirements = [x.strip() for x in open("requirements.txt", "r").readlines()]
requirements = [f"{line.split('#egg=')[-1]} @ {line}" if "#egg=" in line else line for line in requirements]

setup(
    name='gitfive',
    version='1.1.1',
    packages=find_packages(include=['gitfive', 'gitfive.*']),
    license='MPL-2.0',
    license_files = ('LICENSE.md'),
    author='mxrch',
    author_email='mxrch.dev@pm.me',
    description='Track down GitHub users.',
    long_description='GitFive is an OSINT tool designed to retrieve a maximum informations on a GitHub target.',
    long_description_content_type='text/x-rst',
    url='https://github.com/mxrch/gitfive',
    keywords=["osint", "pentest", "cybersecurity", "investigation", "hideandsec", "malfrats"],
    entry_points={
        'console_scripts': [
            'gitfive = gitfive.gitfive:main'
        ]
    },
    install_requires=requirements
)
