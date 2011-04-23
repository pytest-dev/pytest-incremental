from distutils.core import setup

setup(name = 'pytest-doit',
      description = 'a pytest plugin to collect only "outdated" test files',
      version = '0.1.dev',
      license = 'MIT',
      author = 'Eduardo Naufel Schettino',
      author_email = 'schettino72@gmail.com',
      url = 'https://bitbucket.org/schettino72/pytest-doit',
      classifiers = ['Development Status :: 3 - Alpha',
                     'Environment :: Console',
                     'Intended Audience :: Developers',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Operating System :: OS Independent',
                     'Operating System :: POSIX',
                     'Programming Language :: Python :: 2',
                     'Programming Language :: Python :: 2.6',
                     'Programming Language :: Python :: 2.7',
                     'Topic :: Software Development :: Testing',
                     ],
      py_modules = ['pytest_doit'],
      install_requires = ['doit', 'pytest'],
      entry_points = {
        'pytest11': ['pytest_doit = pytest_doit'],
        },
      )

