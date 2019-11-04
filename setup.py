from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_desc = fh.read()

setup(
    name='pyfaz',
    version='0.0.1',
    packages=find_packages(),
    url='https://github.com/Ghilli3/pyFAZ',
    license='Apache 2.0',
    author='Ghilli3',
    author_email='awelsh@fortinet.com',
    description='Represents the base components of the Fortinet FortiAnalyzer JSON-RPC interface',
    long_description=long_desc,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=['requests']
)
