from setuptools import setup, find_packages
# import os, sys


def parse_requirements(requirements):
    # load from requirements.txt
    with open(requirements) as f:
        lines = [l for l in f]
        # remove spaces
        stripped = map((lambda x: x.strip()), lines)
        # remove comments
        nocomments = filter((lambda x: not x.startswith('#')), stripped)
        # remove empty lines
        reqs = filter((lambda x: x), nocomments)
        return reqs

PACKAGE_NAME = "PyDejavu"
PACKAGE_VERSION = "0.1"
SUMMARY = 'Dejavu Audio Fingerprinting'
DESCRIPTION = """Dejavu Audio Fingerprinting"""
REQUIREMENTS = parse_requirements("requirements.txt")

setup(
    name=PACKAGE_NAME,
    version=PACKAGE_VERSION,
    description=SUMMARY,
    long_description=DESCRIPTION,
    author='worldveil',
    author_email='will.drevo@gmail.com',
    url='http://github.com/tuxdna/dejavu',
    license='Apache 2.0',
    include_package_data=True,
    packages=find_packages(),
    platforms=['Any'],
    install_requires=REQUIREMENTS,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
