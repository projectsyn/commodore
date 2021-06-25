"""
Commodore. Build dynamic inventories and compile catalogs with Kapitan
"""
from pathlib import Path as P
from importlib_metadata import version

__url__ = "https://github.com/projectsyn/commodore/"
__git_version__ = "0"
__version__ = version("syn-commodore")

# provide Commodore installation dir as variable that can be imported
__install_dir__ = P(__file__).parent
