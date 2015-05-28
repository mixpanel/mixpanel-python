Run tests::

  tox

Publish to PyPI::

  python setup.py sdist bdist_wheel
  twine upload dist/*

Build docs::

  python setup.py build_sphinx

Publish docs to GitHub Pages::

  ghp-import -n -p build/sphinx/html
