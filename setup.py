from codecs import open
from os import path
from setuptools import setup, find_packages

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='mixpanel-py',
    version='4.0.2',
    description='Official Mixpanel library for Python',
    long_description=long_description,
    url='https://github.com/mixpanel/mixpanel-python',
    author='Mixpanel, Inc.',
    author_email='dev@mixpanel.com',
    license='Apache',

    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2 :: Only',
    ],

    keywords='mixpanel analytics',
    packages=find_packages(),
)
