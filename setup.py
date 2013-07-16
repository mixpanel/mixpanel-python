from distutils.core import setup

setup(
    name='mixpanel-py',
    version='1.0.0',
    author='Amy Quispe',
    author_email='amy@mixpanel.com',
    packages=['mixpanel', 'mixpanel.test'],
    url='http://pypi.python.org/pypi/mixpanel-py/',
    license='LICENSE.txt',
    description='Official Mixpanel library for Python',
    long_description=open('README.txt').read(),
    install_requires=[
    ],
)
