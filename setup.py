import os.path

from distutils.core import setup


with open(os.path.join(os.path.dirname(__file__), 'README.rst'), 'r') as fp:
    README_TEXT = fp.read()


setup(name = 'pytest-incremental',
      description = 'an incremental test runner (pytest plugin)',
      version = '0.4.2',
      license = 'MIT',
      author = 'Eduardo Naufel Schettino',
      author_email = 'schettino72@gmail.com',
      url = 'https://pytest-incremental.readthedocs.io',
      classifiers = ['Development Status :: 3 - Alpha',
                     'Environment :: Console',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Operating System :: OS Independent',
                     'Operating System :: POSIX',
                     'Programming Language :: Python :: 2',
                     'Programming Language :: Python :: 2.7',
                     'Programming Language :: Python :: 3',
                     'Programming Language :: Python :: 3.4',
                     'Topic :: Software Development :: Testing',
                     ],
      py_modules = ['pytest_incremental'],
      install_requires = [
          'six',
          'doit == 0.28.0',
          'pytest',
      ],
      entry_points = {
        'pytest11': ['pytest_incremental = pytest_incremental'],
        },
      long_description = README_TEXT,
      )

