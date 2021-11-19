from codecs import open
from os import path
import re
from setuptools import setup, find_packages

def read(*paths):
    filename = path.join(path.abspath(path.dirname(__file__)), *paths)
    with open(filename, encoding='utf-8') as f:
        return f.read()

def find_version(*paths):
    contents = read(*paths)
    match = re.search(r'^__version__ = [\'"]([^\'"]+)[\'"]', contents, re.M)
    if not match:
        raise RuntimeError('Unable to find version string.')
    return match.group(1)

setup(
    name='mixpanel',
    version=find_version('mixpanel', '__init__.py'),
    description='Official Mixpanel library for Python',
    long_description=read('README.rst'),
    url='https://github.com/mixpanel/mixpanel-python',
    author='Mixpanel, Inc.',
    author_email='dev@mixpanel.com',
    license='Apache',
    python_requires='>=2.7, !=3.4.*',
    install_requires=[
        'six>=1.9.0',
        'requests>=2.4.2',
        'urllib3',
    ],
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    keywords='mixpanel analytics',
    packages=find_packages(),
)
