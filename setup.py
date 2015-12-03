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

PACKAGE_NAME = "Dejavu"
PACKAGE_VERSION = "0.0.1"
SUMMARY = 'Dejavu: Audio Fingerprinting in Python'
DESCRIPTION = """
Audio fingerprinting and recognition algorithm implemented in Python
"""
REQUIREMENTS = parse_requirements("requirements.txt")

setup(
    name=PACKAGE_NAME,
    version=PACKAGE_VERSION,
    description=SUMMARY,
    long_description=DESCRIPTION,
    author='',
    author_email='',
    maintainer="",
    maintainer_email="",
    url='',
    license='',
    include_package_data=True,
    packages=find_packages(),
    platforms=['Unix'],
    install_requires=REQUIREMENTS,
    classifiers=[
        'Development Status ::  Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords="python, audio, fingerprinting, music, numpy, landmark",
)
