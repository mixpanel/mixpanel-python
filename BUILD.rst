Run tests::

  tox

Publish to PyPI::

  pip install twine wheel
  python setup.py sdist bdist_wheel
  twine upload dist/*

Build docs::

  pip install sphinx
  python setup.py build_sphinx

Publish docs to GitHub Pages::

  pip install ghp-import
  ghp-import -n -p build/sphinx/html
