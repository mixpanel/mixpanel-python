try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='mixpanel-py',
    version='3.1.2',
    author='Mixpanel, Inc.',
    author_email='dev@mixpanel.com',
    packages=['mixpanel'],
    url='https://github.com/mixpanel/mixpanel-python',
    description='Official Mixpanel library for Python',
    long_description=open('README.txt').read(),
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2 :: Only',
    ]
)
