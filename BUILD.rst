Release process::

1. Document all changes in CHANGES.rst.
2. Update __version__ in __init__.py.
3. Update version in docs/conf.py
4. Tag the version in git. (ex: git tag 4.8.2 && git push --tags)
5. Create a release in GitHub. https://github.com/mixpanel/mixpanel-python/releases
6. Rebuild docs and publish to GitHub Pages (if appropriate -- see below)
7. Publish to PyPI. (see below)

Install test  and developer environment modules::
  pip install -e .[test,dev]

Run tests::

  python -m tox - runs all tests against all configured environments in the pyproject.toml

Run tests under code coverage::
  python -m coverage run -m pytest
  python -m coverage report -m
  python -m coverage html

Publish to PyPI::

  python -m build
  python -m twine upload dist/*

Build docs::

  python -m sphinx -b html docs docs/_build/html

Publish docs to GitHub Pages::

  python -m ghp_import -n -p docs/_build/html
