Release process::

1. Document all changes in CHANGES.rst.
2. Tag in git.
3. Create a release in github.
4. Rebuild docs and publish to GitHub Pages (if appropriate -- see below)
5. Publish to PyPI. (see below)

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
