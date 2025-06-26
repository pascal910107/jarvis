"""Setup configuration for Jarvis AGI Agent."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read requirements
requirements = []
with open("requirements.txt") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            # Remove version specifiers for install_requires
            pkg = line.split("==")[0].split(">=")[0].split("~=")[0]
            requirements.append(line)

# Development dependencies
dev_requirements = [
    "pytest>=8.4.1",
    "pytest-cov>=6.2.1",
    "black>=25.1.0",
    "flake8>=7.3.0",
    "mypy>=1.16.1",
    "bandit>=1.7.5",
    "safety>=2.3.5",
]

setup(
    name="jarvis-agi",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A modular AGI agent system with cognitive architecture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/jarvis",
    project_urls={
        "Bug Tracker": "https://github.com/yourusername/jarvis/issues",
        "Documentation": "https://github.com/yourusername/jarvis/wiki",
        "Source Code": "https://github.com/yourusername/jarvis",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    packages=find_packages(exclude=["tests", "tests.*", "docs", "docs.*"]),
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        "dev": dev_requirements,
    },
    entry_points={
        "console_scripts": [
            "jarvis=core.main:main",
        ],
    },
    package_data={
        "": ["*.yaml", "*.yml", "*.json"],
    },
    include_package_data=True,
)