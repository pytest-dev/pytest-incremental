import os.path

from distutils.core import setup


with open(os.path.join(os.path.dirname(__file__), 'README.rst'), 'r') as fp:
    README_TEXT = fp.read()


setup(name = 'pytest-incremental',
      description = 'an incremental test runner (pytest plugin)',
      version = '0.6.0',
      license = 'MIT',
      author = 'Eduardo Naufel Schettino',
      author_email = 'schettino72@gmail.com',
      url = 'https://pytest-incremental.readthedocs.io',
      classifiers = ['Development Status :: 5 - Production/Stable',
                     'Environment :: Console',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Operating System :: OS Independent',
                     'Operating System :: POSIX',
                     'Programming Language :: Python :: 3',
                     'Programming Language :: Python :: 3.6',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     'Topic :: Software Development :: Testing',
                     ],
      py_modules = ['pytest_incremental'],
      install_requires = [
          'import_deps >= 0.1.0',
          'doit >= 0.31.1',
          'pytest >= 6.0',
      ],
      entry_points = {
        'pytest11': ['pytest_incremental = pytest_incremental'],
        },
      long_description = README_TEXT,
      keywords = "pytest unittest test",
      project_urls = {
          'Documentation': 'https://pytest-incremental.readthedocs.io',
          'Source': 'https://github.com/pytest-dev/pytest-incremental',
          'Tracker': 'https://github.com/pytest-dev/pytest-incremental/issues',
      },
      )

