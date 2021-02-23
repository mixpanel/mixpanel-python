# -*- coding: utf-8 -*-
import sys
import os

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('..'))

extensions = [
    'sphinx.ext.autodoc',
]
autodoc_member_order = 'bysource'

templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'

# General information about the project.
project = u'mixpanel'
copyright = u' 2021, Mixpanel, Inc.'
author = u'Mixpanel <dev@mixpanel.com>'
version = release = '4.8.2'
exclude_patterns = ['_build']
pygments_style = 'sphinx'


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'alabaster'
html_theme_options = {
    'description': 'The official Mixpanel client library for Python.',
    'github_user': 'mixpanel',
    'github_repo': 'mixpanel-python',
    'github_button': False,
    'travis_button': True,
}

# Custom sidebar templates, maps document names to template names.
html_sidebars = {
    '**': [
        'about.html', 'localtoc.html', 'searchbox.html',
    ]
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_style = 'mixpanel.css'

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
# html_extra_path = []
