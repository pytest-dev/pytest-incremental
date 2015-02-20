from distutils.core import setup

_readme = open('README.rst', 'r')
README_TEXT = _readme.read()
_readme.close()

setup(name = 'pytest-incremental',
      description = 'an incremental test runner (pytest plugin)',
      version = '0.4.dev',
      license = 'MIT',
      author = 'Eduardo Naufel Schettino',
      author_email = 'schettino72@gmail.com',
      url = 'https://pypi.python.org/pypi/pytest-incremental',
      classifiers = ['Development Status :: 3 - Alpha',
                     'Environment :: Console',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Operating System :: OS Independent',
                     'Operating System :: POSIX',
                     'Programming Language :: Python :: 2',
                     'Programming Language :: Python :: 2.7',
                     'Topic :: Software Development :: Testing',
                     ],
      py_modules = ['pytest_incremental'],
      install_requires = [
          'doit >= 0.27.0',
          'pytest',
          'pytest-xdist',
      ],
      entry_points = {
        'pytest11': ['pytest_incremental = pytest_incremental'],
        },
      long_description = README_TEXT,
      )

