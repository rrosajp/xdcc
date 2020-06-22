import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="xdcc",
    version="0.0.2",
    author="Thiago T. P. Silva",
    author_email="thiagoteodoro501@gmail.com",
    description="A simple XDCC downloader written in python3",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/thiagotps/xdcc",
    packages=setuptools.find_packages(),
    install_requires = ['irc'],
    keywords="irc xdcc",
    entry_points={"console_scripts": ["xdcc=xdcc.__main__:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)
