"""
This file is used to configure your package for distribution.
It tells python how to install your package, what dependencies it has, and what scripts to run.

"""

from setuptools import find_packages, setup

setup(
    name="ocp-diag-autoval-ssd",
    version="0.1.0",
    Packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "ocp-diag-autoval>=0.1.0",
    ],
    description="Autoval SSD OCP Diag - SSD specific test for Autoval",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/opencomputeproject/ocp-diag-autoval-ssd",
    python_requires=">=3.10",
)
