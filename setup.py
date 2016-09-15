from setuptools import setup

setup(name='jollyae',
      version='0.1',
      description='A directory queue to S3 adaptor',
      url='http://github.com/jbm/jollyae',
      author='Josh Myer',
      author_email='josh@joshisanerd.com',
      license='MIT',
      packages=[],
      install_requires=[
          'boto',
          'watchdog',
          
      ],
      scripts=["jollyae.py"],
      zip_safe=False)
