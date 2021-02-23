Release process::

1. Document all changes in CHANGES.rst.
2. Update __version__ in __init__.py.
3. Update version in docs/conf.py
4. Tag the version in git. (ex: git tag 4.8.2 && git push --tags)
5. Create a release in GitHub. https://github.com/mixpanel/mixpanel-python/releases
6. Rebuild docs and publish to GitHub Pages (if appropriate -- see below)
7. Publish to PyPI. (see below)

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
